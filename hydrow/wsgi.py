from app import create_app
from werkzeug.middleware.proxy_fix import ProxyFix

application = create_app()

# Behind Cloudflare → Traefik → svclb → app, X-Forwarded-For arrives as
# "<client>, <svclb-pod>" (Traefik appends the connecting peer). x_for=2
# skips the svclb hop and pins REMOTE_ADDR to the real client.
application.wsgi_app = ProxyFix(
    application.wsgi_app,
    x_for=2,
    x_proto=1,
    x_host=1,
)

if __name__ == "__main__":
    application.run()