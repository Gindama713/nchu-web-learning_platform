"""Single Web process / bounded threads; real grader runs separately."""

import os


def main():
    os.environ.setdefault("SERVE_DIST", "1")
    from waitress import serve

    from backend.app import app

    serve(app, host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "8000")),
          threads=int(os.environ.get("WEB_THREADS", "8")), max_request_body_size=128 * 1024 * 1024,
          clear_untrusted_proxy_headers=True)


if __name__ == "__main__":
    main()
