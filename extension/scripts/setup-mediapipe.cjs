const fs = require('fs');
const path = require('path');
const https = require('https');

// ---- WASM files ----
const wasmSrc  = path.join(__dirname, '../node_modules/@mediapipe/tasks-vision/wasm');
const wasmDest = path.join(__dirname, '../public/mediapipe/wasm');

if (!fs.existsSync(wasmDest)) fs.mkdirSync(wasmDest, { recursive: true });

for (const file of fs.readdirSync(wasmSrc)) {
  const dest = path.join(wasmDest, file);
  if (!fs.existsSync(dest)) {
    fs.copyFileSync(path.join(wasmSrc, file), dest);
    console.log('[setup] Copied WASM:', file);
  } else {
    console.log('[setup] WASM already present:', file);
  }
}

// ---- Models ----
const MODELS = [
  {
    url: 'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task',
    name: 'face_landmarker.task'
  },
  {
    url: 'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task',
    name: 'hand_landmarker.task'
  }
];

const modelDir = path.join(__dirname, '../public/mediapipe');
if (!fs.existsSync(modelDir)) fs.mkdirSync(modelDir, { recursive: true });

function download(url, dest, name, redirects = 0) {
  if (redirects > 5) { console.error(`[setup] Too many redirects for ${name}`); process.exit(1); }
  const file = fs.createWriteStream(dest);
  https.get(url, (res) => {
    if (res.statusCode === 301 || res.statusCode === 302) {
      file.close(() => fs.unlinkSync(dest));
      download(res.headers.location, dest, name, redirects + 1);
      return;
    }
    if (res.statusCode !== 200) {
      file.close(() => fs.unlinkSync(dest));
      console.error(`[setup] Download failed for ${name}, status:`, res.statusCode);
      process.exit(1);
    }
    res.pipe(file);
    file.on('finish', () => {
      file.close(() => console.log(`[setup] ${name} downloaded.`));
    });
  }).on('error', (err) => {
    fs.unlinkSync(dest);
    console.error(`[setup] Download error for ${name}:`, err.message);
    process.exit(1);
  });
}

for (const model of MODELS) {
  const dest = path.join(modelDir, model.name);
  if (fs.existsSync(dest)) {
    console.log(`[setup] Model already present: ${model.name}`);
  } else {
    console.log(`[setup] Downloading ${model.name}…`);
    download(model.url, dest, model.name);
  }
}
