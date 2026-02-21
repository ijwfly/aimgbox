import sys


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m aimg <api|worker|admin>")
        sys.exit(1)

    command = sys.argv[1]

    if command == "api":
        import uvicorn

        uvicorn.run(
            "aimg.api.app:create_app",
            factory=True,
            host="0.0.0.0",
            port=8000,
            log_level="info",
        )
    elif command == "worker":
        from aimg.worker.main import main as worker_main

        worker_main()
    elif command == "admin":
        import uvicorn

        uvicorn.run(
            "aimg.admin.app:create_admin_app",
            factory=True,
            host="0.0.0.0",
            port=8001,
            log_level="info",
        )
    else:
        print(f"Unknown command: {command}")
        print("Usage: python -m aimg <api|worker|admin>")
        sys.exit(1)


main()
