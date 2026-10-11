document.getElementById('requestBtn').addEventListener('click', function () {
  var statusEl = document.getElementById('status');
  statusEl.style.display = 'block';
  statusEl.innerText = 'Requesting permission... look for the browser prompt at top of this page.';
  statusEl.style.backgroundColor = '#e9ecef';
  statusEl.style.color = '#333';

  navigator.mediaDevices.getUserMedia({ video: true, audio: true })
    .then(function (stream) {
      statusEl.innerText = '\u2705 Permission granted! Closing this tab and starting camera...';
      statusEl.style.backgroundColor = '#d4edda';
      statusEl.style.color = '#155724';
      // Stop tracks immediately — we only needed the grant
      stream.getTracks().forEach(function (track) { track.stop(); });
      // Auto-close tab so user returns to original site
      setTimeout(function () { window.close(); }, 1500);
    })
    .catch(function (err) {
      statusEl.innerText = '\u274C Permission denied (' + err.name + '). Click the camera icon in the address bar to allow access, then try again.';
      statusEl.style.backgroundColor = '#f8d7da';
      statusEl.style.color = '#721c24';
    });
});
