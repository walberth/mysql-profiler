from waitress import serve

from webapp import create_app


def main():
    app, settings = create_app()
    print(f"[web] Listening on http://{settings.web_host}:{settings.web_port}")
    serve(
        app,
        host=settings.web_host,
        port=settings.web_port,
        threads=8,
        ident="mysql-profiler",
    )


if __name__ == "__main__":
    main()
