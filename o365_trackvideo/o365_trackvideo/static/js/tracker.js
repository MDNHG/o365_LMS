/*
 * tracker.js - theo dõi tiến độ xem video YouTube cho LMS o365.
 *  - Cho tua lùi, chặn tua vượt mốc xem xa nhất (furthest reached).
 *  - Gửi heartbeat 30s/lần + khi pause / seek / kết thúc / ẩn tab / rời trang.
 *  - Sau N phút không tương tác: tạm dừng video và hỏi "Bạn có còn đang xem không?".
 *  - Giảng viên/admin xem thử: không ghi tiến độ, chỉ đồng bộ thời lượng thật của video.
 */
(function () {
  'use strict';

  var root = document.getElementById('lms-video-tracker');
  if (!root) return;

  var d = root.dataset;
  var cfg = {
    lessonId: parseInt(d.lessonId, 10),
    videoId: d.videoId,
    mode: d.mode,
    canSync: d.canSync === '1',
    heartbeatUrl: d.heartbeatUrl,
    syncUrl: d.syncUrl,
    eventUrl: d.eventUrl,
    csrf: d.csrf,
    duration: parseInt(d.duration, 10) || 0,
    threshold: parseFloat(d.threshold) || 80,
    furthest: parseInt(d.furthest, 10) || 0,
    percent: parseFloat(d.percent) || 0,
    completed: d.completed === '1',
    heartbeatMs: (parseInt(d.heartbeatSeconds, 10) || 30) * 1000,
    seekTolerance: parseInt(d.seekTolerance, 10) || 3,
    idleMs: (parseFloat(d.idleMinutes) || 15) * 60 * 1000,
    countdown: parseInt(d.countdownSeconds, 10) || 60,
    seekPolicy: d.seekPolicy || 'backward_only',
    allowSpeed: d.allowSpeed !== '0',
    maxSpeed: parseFloat(d.maxSpeed) || 2.0,
    tickMs: 500
  };

  var isStudent = cfg.mode === 'student';
  var tracking = isStudent && cfg.duration > 0;

  function $(id) { return document.getElementById(id); }
  var el = {
    bar: $('lms-progress-bar'), track: $('lms-progress-track'), text: $('lms-progress-text'),
    badge: $('lms-completed-badge'), toast: $('lms-toast'), error: $('lms-error'),
    modal: $('lms-idle-modal'), count: $('lms-idle-count'), idleText: $('lms-idle-text'),
    btn: $('lms-idle-continue')
  };

  // ---------- Trạng thái ----------
  var player = null;
  var furthest = cfg.furthest;      // mốc xem xa nhất (giây)
  var segStart = 0, segEnd = 0;     // đoạn đang phát liên tục chưa gửi
  var lastT = 0, lastWall = 0;      // vị trí + thời điểm của lần tick trước (để phát hiện seek)
  var playing = false;
  var modalOpen = false;
  var locked = false;               // hết thời gian chờ xác nhận: ngừng ghi nhận
  var selfPaused = false;           // phân biệt pause do hệ thống với pause do học viên
  var lastActivity = Date.now();
  var countdownTimer = null;
  var toastTimer = null;
  var queue = Promise.resolve();
  var completedShown = cfg.completed;

  // ---------- Giao diện ----------
  function updateUI(percent, completed) {
    if (!el.bar) return;
    var p = Math.max(0, Math.min(100, percent));
    el.bar.style.width = p + '%';
    if (el.track) el.track.setAttribute('aria-valuenow', Math.round(p));
    el.text.textContent = 'Đã xem ' + Math.round(p) + '% (cần đạt ' + cfg.threshold + '%)';
    if (el.badge) el.badge.hidden = !completed;
  }

  function toast(msg) {
    if (!el.toast) return;
    el.toast.textContent = msg;
    el.toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.toast.hidden = true; }, 4500);
  }

  function showError(msg) {
    if (!el.error) return;
    el.error.textContent = msg;
    el.error.hidden = false;
  }

  function beep() {
    try {
      var Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return;
      var ctx = new Ctx();
      var osc = ctx.createOscillator();
      var gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.value = 880;
      gain.gain.value = 0.08;
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.35);
      osc.onended = function () { ctx.close(); };
    } catch (e) { /* trình duyệt chặn âm thanh: bỏ qua */ }
  }

  // ---------- Mạng ----------
  function post(url, body, keepalive) {
    return fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      keepalive: !!keepalive,
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': cfg.csrf,
        'X-Requested-With': 'XMLHttpRequest'
      },
      body: JSON.stringify(body)
    });
  }

  function delay(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

  function sendWithRetry(payload, tries) {
    return post(cfg.heartbeatUrl, payload, false).then(function (r) {
      if (r.status === 401) {
        toast('Phiên đăng nhập đã hết hạn. Hãy tải lại trang và đăng nhập lại.');
        return null;
      }
      if (r.status >= 500 && tries > 1) {
        return delay(2000).then(function () { return sendWithRetry(payload, tries - 1); });
      }
      return r.json().then(handleResponse);
    }).catch(function () {
      if (tries > 1) {
        return delay(2000).then(function () { return sendWithRetry(payload, tries - 1); });
      }
    });
  }

  // Gửi sự kiện tương tác lên server để lưu vết Audit Log
  function logEvent(eventType, videoTime, extra) {
    if (!tracking || !cfg.eventUrl) return;
    var payload = {
      lesson_id: cfg.lessonId,
      event_type: eventType,
      video_time: videoTime !== undefined ? videoTime : Math.floor(safeTime()),
      extra_data: extra || {}
    };
    post(cfg.eventUrl, payload, false).catch(function () {});
  }

  // Gửi theo hàng đợi để server nhận đúng thứ tự (server kiểm tra interval theo mốc furthest).
  function send(start, end, reason, opts) {
    opts = opts || {};
    var payload = {
      lesson_id: cfg.lessonId,
      interval: [start, end],
      current_time: Math.floor(safeTime()),
      tab_hidden: opts.hidden !== undefined ? opts.hidden : document.hidden,
      reason: reason
    };
    if (opts.keepalive) {            // rời trang: gửi ngay, không chờ hàng đợi
      post(cfg.heartbeatUrl, payload, true).catch(function () {});
      return;
    }
    queue = queue.then(function () { return sendWithRetry(payload, 3); });
  }

  function handleResponse(res) {
    if (!res || res.ok === false) return;
    if (res.tracked === false) { tracking = false; return; }

    if (typeof res.furthest === 'number') {
      if (res.accepted === false && res.reason === 'gap') {
        // Server không nhận khoảng này: lấy mốc của server làm chuẩn.
        furthest = res.furthest;
        if (player && safeTime() > furthest + cfg.seekTolerance) forceBack();
      } else if (res.furthest > furthest) {
        furthest = res.furthest;
      }
    }
    if (res.reason === 'no_duration') {
      tracking = false;
      showError('Bài học chưa có thời lượng nên tiến độ chưa được ghi nhận. Hãy báo giảng viên.');
    }
    if (typeof res.completion_percentage === 'number') {
      updateUI(res.completion_percentage, !!res.is_completed);
    }
    if (res.is_completed && !completedShown) {
      completedShown = true;
      toast('Chúc mừng, bạn đã hoàn thành bài học này!');
    }
  }

  // ---------- Theo dõi đoạn đang phát ----------
  function safeTime() {
    try { return player.getCurrentTime() || 0; } catch (e) { return 0; }
  }

  function startSegment(t) {
    segStart = segEnd = lastT = t;
    lastWall = Date.now();
  }

  function flushSegment(reason, opts) {
    if (!tracking) return;
    var s = Math.floor(segStart);
    var e = Math.floor(segEnd);
    segStart = segEnd;
    if (locked || e - s < 1) return;
    send(s, e, reason, opts);
  }

  function forceBack() {
    try { player.seekTo(furthest, true); } catch (e) { /* bỏ qua */ }
    toast('Bạn chỉ có thể tua lại phần đã học, không thể tua vượt qua phần chưa xem.');
    startSegment(furthest);
  }

  function enforcePlaybackRate() {
    if (!player || typeof player.getPlaybackRate !== 'function') return;
    var rate = player.getPlaybackRate() || 1.0;
    if (!cfg.allowSpeed && rate > 1.0) {
      player.setPlaybackRate(1.0);
      toast('Bài học này yêu cầu xem ở tốc độ chuẩn 1.0x.');
      logEvent('speed_change', safeTime(), { attempted_rate: rate, enforced: 1.0 });
    } else if (rate > cfg.maxSpeed) {
      player.setPlaybackRate(cfg.maxSpeed);
      toast('Tốc độ phát tối đa cho phép là ' + cfg.maxSpeed + 'x.');
      logEvent('speed_change', safeTime(), { attempted_rate: rate, enforced: cfg.maxSpeed });
    }
  }

  function handleSeek(targetTime) {
    var fromTime = lastT;
    if (cfg.seekPolicy === 'none') {
      try { player.seekTo(fromTime, true); } catch (e) {}
      toast('Bài giảng này giáo viên yêu cầu xem liền mạch, không được phép tua.');
      logEvent('seek_forward', targetTime, { from: fromTime, to: targetTime, suspicious: true, policy: 'none' });
      startSegment(fromTime);
      return;
    }
    if (cfg.seekPolicy === 'backward_only') {
      if (targetTime < fromTime) {
        logEvent('seek_backward', targetTime, { from: fromTime, to: targetTime });
        startSegment(targetTime);
      } else if (targetTime > furthest + cfg.seekTolerance) {
        forceBack();
        logEvent('seek_forward', targetTime, { from: fromTime, to: targetTime, suspicious: true, furthest: furthest });
      } else {
        startSegment(targetTime);
      }
      return;
    }
    // Cho tua tự do
    logEvent(targetTime > fromTime ? 'seek_forward' : 'seek_backward', targetTime, { from: fromTime, to: targetTime });
    startSegment(targetTime);
  }

  function tick() {
    if (!player || typeof player.getCurrentTime !== 'function') return;
    enforcePlaybackRate();
    var t = safeTime();
    var now = Date.now();

    if (playing) {
      var rate = player.getPlaybackRate() || 1;
      var elapsed = (now - lastWall) / 1000;
      var expected = lastT + elapsed * rate;
      var tolerance = 2 + elapsed * 0.1;   // tab nền bị giảm tần suất timer vẫn không báo nhầm
      if (Math.abs(t - expected) <= tolerance) {
        segEnd = t; lastT = t; lastWall = now;           // phát tự nhiên
        if (tracking && t > furthest) furthest = t;
        return;
      }
      // Phát hiện học viên tua (seek): chốt đoạn cũ, rồi kiểm tra điểm đến.
      flushSegment('seek');
      handleSeek(t);
      return;
    }
    // Đang dừng:
    if (tracking) {
      if (cfg.seekPolicy === 'none' && Math.abs(t - lastT) > 2) {
        try { player.seekTo(lastT, true); } catch (e) {}
        toast('Bài giảng này yêu cầu xem liền mạch, không được phép tua.');
      } else if (cfg.seekPolicy === 'backward_only' && t > furthest + cfg.seekTolerance) {
        forceBack();
      }
    }
  }

  function enterPlaying() {
    var t = safeTime();
    playing = true;
    enforcePlaybackRate();
    if (tracking) {
      if (cfg.seekPolicy === 'none' && lastT > 0 && Math.abs(t - lastT) > 2) {
        try { player.seekTo(lastT, true); } catch (e) {}
        t = lastT;
      } else if (t > furthest + cfg.seekTolerance) {
        forceBack();
        return;
      }
    }
    logEvent('play', t);
    startSegment(t);
  }

  function leavePlaying(reason, refine) {
    if (!playing) return;
    if (reason === 'ended') {
      var dur = 0;
      try { dur = player.getDuration() || 0; } catch (e) { /* bỏ qua */ }
      if (dur - segEnd <= 3) segEnd = dur;
      if (tracking && dur > furthest && dur - furthest <= cfg.seekTolerance + 3) furthest = dur;
      logEvent('stop', dur);
    } else if (reason === 'pause') {
      logEvent('pause', safeTime());
    } else if (refine) {
      var t = safeTime();
      if (t >= segEnd && t - segEnd <= 3) segEnd = t;
    }
    playing = false;
    flushSegment(reason);
  }

  // ---------- Không tương tác ----------
  function markActive() {
    if (!modalOpen) lastActivity = Date.now();
  }

  function checkIdle() {
    if (!tracking || !playing || modalOpen || locked) return;
    if (Date.now() - lastActivity >= cfg.idleMs) showIdleModal();
  }

  function showIdleModal() {
    modalOpen = true;
    if (document.fullscreenElement && document.exitFullscreen) {
      try { document.exitFullscreen(); } catch (e) { /* bỏ qua */ }
    }
    selfPaused = true;
    player.pauseVideo();
    logEvent('inactivity_prompt', safeTime());

    var remain = cfg.countdown;
    el.count.textContent = remain;
    el.btn.textContent = 'Tôi vẫn đang xem';
    el.modal.hidden = false;
    el.btn.focus();
    beep();

    clearInterval(countdownTimer);
    countdownTimer = setInterval(function () {
      remain -= 1;
      el.count.textContent = Math.max(remain, 0);
      if (remain <= 0) {
        clearInterval(countdownTimer);
        locked = true;   // ngừng ghi nhận cho tới khi học viên xác nhận
        logEvent('inactivity_timeout', safeTime());
        el.idleText.textContent =
          'Phiên xem đã tạm dừng vì bạn không phản hồi. Bấm nút bên dưới để tiếp tục xem.';
        el.btn.textContent = 'Tiếp tục xem';
      }
    }, 1000);
  }

  function confirmStillWatching() {
    clearInterval(countdownTimer);
    modalOpen = false;
    locked = false;
    el.modal.hidden = true;
    lastActivity = Date.now();
    logEvent('inactivity_confirmed', safeTime());
    player.playVideo();
  }

  // ---------- Trình phát YouTube ----------
  function onStateChange(e) {
    var S = YT.PlayerState;
    if (e.data === S.PLAYING) {
      if (modalOpen || locked) { selfPaused = true; player.pauseVideo(); return; }
      markActive();
      enterPlaying();
    } else if (e.data === S.PAUSED) {
      leavePlaying('pause', true);
      if (selfPaused) selfPaused = false; else markActive();
    } else if (e.data === S.ENDED) {
      leavePlaying('ended', false);
    } else if (e.data === S.BUFFERING) {
      leavePlaying('buffer', false);
    }
  }

  function onError(e) {
    var msgs = {
      2: 'Liên kết video không hợp lệ.',
      5: 'Trình phát gặp lỗi. Hãy thử tải lại trang.',
      100: 'Video không tồn tại, đã bị xóa hoặc đặt ở chế độ riêng tư.',
      101: 'Chủ video không cho phép nhúng video này.',
      150: 'Chủ video không cho phép nhúng video này.'
    };
    showError(msgs[e.data] || 'Không phát được video này.');
  }

  function syncDuration() {
    var tries = 0;
    (function attempt() {
      var dur = Math.round(player.getDuration() || 0);
      if (dur <= 0) {
        if (tries++ < 15) setTimeout(attempt, 1000);
        return;
      }
      if (Math.abs(dur - cfg.duration) < 2) return;
      post(cfg.syncUrl, { lesson_id: cfg.lessonId, duration: dur }, false)
        .then(function (r) { return r.json(); })
        .then(function (res) {
          if (res && res.ok) {
            cfg.duration = dur;
            toast('Đã cập nhật thời lượng video: ' + dur + ' giây.');
          }
        }).catch(function () {});
    })();
  }

  function onReady() {
    updateUI(cfg.percent, cfg.completed);

    if (cfg.mode === 'preview') {
      if (cfg.canSync) syncDuration();
      return;
    }
    if (!tracking) {
      showError('Bài học chưa có thời lượng nên tiến độ chưa được ghi nhận. Hãy báo giảng viên.');
      return;
    }

    setInterval(tick, cfg.tickMs);
    setInterval(checkIdle, 5000);
    setInterval(function () {
      if (!tracking || !playing || locked) return;
      tick();
      if (playing) flushSegment('heartbeat');
    }, cfg.heartbeatMs);

    ['mousemove', 'keydown', 'click', 'scroll', 'touchstart'].forEach(function (evt) {
      document.addEventListener(evt, markActive, { passive: true });
    });
    // Bấm vào bên trong iframe không nổi bọt lên trang, nhưng cửa sổ sẽ mất focus.
    window.addEventListener('blur', function () {
      if (document.activeElement && document.activeElement.tagName === 'IFRAME') markActive();
    });
    el.btn.addEventListener('click', confirmStillWatching);

    // Ẩn/hiện tab: chốt đoạn đang phát, gắn cờ trạng thái tab của đoạn vừa kết thúc.
    document.addEventListener('visibilitychange', function () {
      if (tracking && playing) {
        tick();
        flushSegment('visibility', { hidden: !document.hidden });
      }
      if (tracking) {
        logEvent(document.hidden ? 'tab_hidden' : 'tab_visible', safeTime());
      }
    });
    // Rời trang: gửi nốt phần còn lại.
    window.addEventListener('pagehide', function () {
      if (tracking && playing) { tick(); flushSegment('unload', { keepalive: true }); }
    });
  }

  function initPlayer() {
    player = new YT.Player('lms-yt-player', {
      videoId: cfg.videoId,
      playerVars: {
        rel: 0,
        modestbranding: 1,
        playsinline: 1,
        origin: window.location.origin
      },
      events: {
        onReady: onReady,
        onStateChange: onStateChange,
        onPlaybackRateChange: function () {
          enforcePlaybackRate();
        },
        onError: onError
      }
    });
  }

  function loadApi() {
    if (window.YT && window.YT.Player) { initPlayer(); return; }
    var prev = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = function () {
      if (typeof prev === 'function') prev();
      initPlayer();
    };
    var s = document.createElement('script');
    s.src = 'https://www.youtube.com/iframe_api';
    document.head.appendChild(s);
  }

  loadApi();
})();
