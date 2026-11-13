# aws-rum-web (vendored)

`cwr.js` is the Amazon CloudWatch RUM web client 1.x, downloaded unchanged on
13/11/2026 from `https://client.rum.us-east-1.amazonaws.com/1.x/cwr.js`
(Last-Modified 23/07/2025, ETag `99102e6303a7844b22c4179d59acab44`).

License: Apache-2.0, https://github.com/aws-observability/aws-rum-web.

It is served from the site itself because the Content-Security-Policy allows
scripts only from `'self'`. `../../rum.js` loads it after the page is idle,
and only when `rum-config.json` exists.
