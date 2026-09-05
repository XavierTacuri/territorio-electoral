// One-off generator for the PWA app icons: solid brand-color squares with a
// simple centered "T" mark, encoded as raw PNG via zlib (no image deps needed).
import { deflateSync } from 'node:zlib';
import { writeFileSync } from 'node:fs';

const BG = [0x24, 0x4b, 0x5a]; // theme color #244b5a
const FG = [0xff, 0xff, 0xff];

function crc32(buf) {
  let c;
  const table = crc32.table ?? (crc32.table = (() => {
    const t = new Uint32Array(256);
    for (let n = 0; n < 256; n++) {
      c = n;
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      t[n] = c >>> 0;
    }
    return t;
  })());
  let crc = 0xffffffff;
  for (let i = 0; i < buf.length; i++) crc = table[(crc ^ buf[i]) & 0xff] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}

function chunk(type, data) {
  const typeBuf = Buffer.from(type, 'ascii');
  const lenBuf = Buffer.alloc(4);
  lenBuf.writeUInt32BE(data.length, 0);
  const crcBuf = Buffer.alloc(4);
  crcBuf.writeUInt32BE(crc32(Buffer.concat([typeBuf, data])), 0);
  return Buffer.concat([lenBuf, typeBuf, data, crcBuf]);
}

function isMark(x, y, size) {
  // A simple centered "T": a horizontal bar and a vertical stem.
  const m = Math.round(size * 0.2);
  const barTop = m;
  const barBottom = m + Math.round(size * 0.12);
  const stemWidth = Math.round(size * 0.14);
  const cx = size / 2;
  if (y >= barTop && y < barBottom && x >= m && x < size - m) return true;
  if (y >= barBottom && y < size - m && x >= cx - stemWidth / 2 && x < cx + stemWidth / 2) return true;
  return false;
}

function makePng(size, { maskablePadding = 0 } = {}) {
  const raw = Buffer.alloc((size * 4 + 1) * size);
  let offset = 0;
  for (let y = 0; y < size; y++) {
    raw[offset++] = 0; // filter type 0 per scanline
    for (let x = 0; x < size; x++) {
      const insidePad =
        x < maskablePadding || y < maskablePadding || x >= size - maskablePadding || y >= size - maskablePadding;
      let rgb = BG;
      if (!insidePad) {
        const innerSize = size - maskablePadding * 2;
        const ix = x - maskablePadding;
        const iy = y - maskablePadding;
        if (isMark(ix, iy, innerSize)) rgb = FG;
      }
      raw[offset++] = rgb[0];
      raw[offset++] = rgb[1];
      raw[offset++] = rgb[2];
      raw[offset++] = 255;
    }
  }
  const compressed = deflateSync(raw, { level: 9 });
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(size, 0);
  ihdr.writeUInt32BE(size, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 6; // color type RGBA
  ihdr[10] = 0;
  ihdr[11] = 0;
  ihdr[12] = 0;
  const signature = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
  return Buffer.concat([signature, chunk('IHDR', ihdr), chunk('IDAT', compressed), chunk('IEND', Buffer.alloc(0))]);
}

writeFileSync('public/icons/icon-192.png', makePng(192));
writeFileSync('public/icons/icon-512.png', makePng(512));
writeFileSync('public/icons/icon-maskable-512.png', makePng(512, { maskablePadding: Math.round(512 * 0.1) }));
console.log('PWA icons generated in public/icons/');
