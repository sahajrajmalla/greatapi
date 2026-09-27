# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| 2.x | Yes |
| 1.x | Security fixes only, until 2027-08 |

1.x contains known vulnerabilities that cannot be fixed without breaking
changes — most importantly a JWT signing key that was published with the
package, and an admin whose authorization check ran only in the browser. If you
are on 1.x, please upgrade. See [MIGRATION.md](MIGRATION.md).

## Reporting a vulnerability

Please report privately, through
[GitHub's private advisory form](https://github.com/sahajrajmalla/greatapi/security/advisories/new),
or by email to mallasahajraj@gmail.com.

Please include:

- what an attacker can do, and what they need in order to do it
- the affected version and the smallest reproduction you can manage
- anything you already know about a fix

You can expect an acknowledgement within three days and an assessment within
seven. If the report is valid, we will agree a disclosure date with you, credit
you in the advisory unless you would rather we did not, and release a fix for
the supported versions.

Please do not open a public issue, and please give us a chance to ship a fix
before disclosing.

## Deploying GreatAPI safely

- **Set `GREATAPI_SECRET_KEY`** from `greatapi generate-secret`, and keep it out
  of source control. The app refuses to start without one unless `DEBUG` is on.
- **Leave `GREATAPI_DEBUG` off** in production. It controls error verbosity,
  whether tables are created on boot, and whether session cookies require HTTPS.
- **Serve over HTTPS.** Session cookies are `Secure` whenever debug is off, and
  will not be sent over plain HTTP.
- **Use migrations, not `create_tables`,** so schema changes are reviewed.
- **Give API keys the narrowest scopes** that work, and set a rate limit and a
  monthly budget on each.
- **Keep the admin off the public internet** if you can — behind a VPN, an IP
  allow-list, or an authenticating proxy.
- The default rate limiter is per-process. Behind several workers, supply a
  shared implementation via `greatapi.keys.set_rate_limiter`.
