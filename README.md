# GPLinks Wrapper API (Render)

A small FastAPI wrapper around the GPLinks Quick Link endpoint.


## Deploy to Render
1. Create a GitHub repository and upload these files to its root.
2. In Render, choose **New → Web Service** and connect the repository.
3. Render detects `render.yaml` (or use Python runtime manually).
4. Add environment variables:
   - `GPLINKS_API_KEY`: your GPLinks Quick Link API key
   - `API_SECRET`: optional secret to protect this wrapper API; choose a long random value
5. Deploy. Your service base URL will look like `https://your-service-name.onrender.com`.


## Endpoints
- `GET /` API info
- `GET /health` health check
- `GET /shorten?url=https://example.com/page`
- `POST /shorten` JSON: `{ "url": "https://example.com/page" }`
- `POST /bulk` JSON: `{ "urls": ["https://example.com/a", "https://example.com/b"] }` (max 50)

If `API_SECRET` is set, send it in header `X-API-Key`.


## Example request
```bash
curl -X POST 'https://YOUR-RENDER-SERVICE.onrender.com/shorten' \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: YOUR_API_SECRET' \
  -d '{"url":"https://example.com/movie-page"}'
```

If you leave `API_SECRET` unset, this wrapper endpoint is public. Keep `GPLINKS_API_KEY` only in Render environment variables; never put it in frontend code or share it.


## Provider response note
GPLinks Quick Link is documented as `https://api.gplinks.com/st?api=YOUR_API_KEY&url=DESTINATION`. The parser accepts a redirect Location, JSON URL fields, or a plain-text URL. If GPLinks changes or returns a different response shape, the wrapper returns a 502 parse error rather than guessing a short URL.
