# Pay.sh gateway (sandbox)

`paywall.yml` puts Data Plumber behind a Pay.sh gateway. The gateway is the only place payment happens. It answers unpaid calls with `402 Payment Required`, verifies the payment, and proxies the request to the API on `127.0.0.1:8000`.

| Endpoint | Price |
|---|---|
| `GET /v1/health` | free |
| `POST /v1/adapt` | $0.02 per request (USDC, 6 decimals: amount `20000`) |

## Run

```powershell
pay --version                                              # tested with 0.26.0
uvicorn app.main:app --host 127.0.0.1 --port 8000          # terminal 1: the API
pay --sandbox gate api pay/paywall.yml --bind 127.0.0.1:1402   # terminal 2: the gateway
```

`--sandbox` uses the Pay.sh sandbox ledger (`https://402.surfnet.dev:8899`) and a funded sandbox wallet, so no real funds are spent. Do not drop `--sandbox` while developing: without it, `pay curl` pays from your mainnet account.

## Acceptance

```powershell
# unpaid -> 402 with a Payment challenge; the API never sees the request
curl.exe -i -X POST http://127.0.0.1:1402/v1/adapt -H "Content-Type: application/json" --data-binary "@examples/acme_request.json"

# forged payment header -> rejected (400/401/402)
curl.exe -i -X POST http://127.0.0.1:1402/v1/adapt -H "Authorization: Payment bogus" -H "Content-Type: application/json" --data-binary "@examples/acme_request.json"

# free route -> 200
curl.exe -s http://127.0.0.1:1402/v1/health

# paid -> 200 with {data, valid, warnings}
pay --sandbox curl -s -X POST http://127.0.0.1:1402/v1/adapt -H "Content-Type:application/json" --data-binary "@examples/acme_request.json"
```

The same checks run automatically:

```powershell
$env:DP_GATEWAY_URL="http://127.0.0.1:1402"; pytest -m gateway
```

Watch the uvicorn log while doing this: only the paid request should show up as `POST /v1/adapt`.

## Notes

- Keep the API bound to `127.0.0.1`. Anything that can reach `:8000` directly skips payment.
- With `pay curl` on Windows, write headers without a space (`Content-Type:application/json`) and send the body from a file (`--data-binary @file`).
- The sandbox can reject two identical back-to-back transfers with "This transaction has already been processed". Retrying a few seconds later works; `clients/paid_http.py` does this automatically.
- In our runs, `pay gate` exited on its own after about 5 minutes. Restart it before a demo.
- Public listing in the Pay.sh catalog needs an HTTPS `service_url`, a mainnet 402 (USDC/USDT), and a PR to `solana-foundation/pay-skills` with `PAY.md` and `openapi.json`. None of that is done here.
