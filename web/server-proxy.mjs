// Custom Next.js dev server that proxies /ws WebSocket to the backend.
// Usage: node server-proxy.mjs
// Allows a single ngrok tunnel (port 3000) to handle both frontend and WS.

import { createServer } from 'http';
import { connect } from 'net';
import next from 'next';

const hostname = process.env.HOSTNAME || '0.0.0.0';
const port = parseInt(process.env.PORT || '3000', 10);
const backendPort = parseInt(process.env.BACKEND_PORT || '8765', 10);

const app = next({ dev: true, hostname, port, turbopack: false });
const handle = app.getRequestHandler();

app.prepare().then(() => {
  const server = createServer((req, res) => handle(req, res));

  // Proxy WebSocket upgrades on /ws to backend via raw TCP tunnel
  server.on('upgrade', (req, clientSocket, head) => {
    if (req.url !== '/ws') { clientSocket.destroy(); return; }

    const backend = connect(backendPort, '127.0.0.1');

    backend.on('connect', () => {
      // Re-send the HTTP Upgrade request to the backend
      const lines = [`GET /ws HTTP/1.1`];
      for (const [k, v] of Object.entries(req.headers)) {
        lines.push(`${k}: ${v}`);
      }
      backend.write(lines.join('\r\n') + '\r\n\r\n');
      if (head?.length) backend.write(head);

      backend.pipe(clientSocket);
      clientSocket.pipe(backend);
    });

    backend.on('error', () => clientSocket.destroy());
    clientSocket.on('error', () => backend.destroy());
  });

  server.listen(port, hostname, () => {
    console.log(`\n> ListenClaw ready on http://${hostname}:${port}`);
    console.log(`> WebSocket /ws → proxied to port ${backendPort}\n`);
  });
});
