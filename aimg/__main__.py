import sys


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m aimg <api|worker|admin|seed|sync-job-types|reconcile-balances>")
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
    elif command == "seed":
        from aimg.scripts.seed import main as seed_main

        seed_main()
    elif command == "sync-job-types":
        from aimg.scripts.sync_job_types import main as sync_main

        sync_main()
    elif command == "reconcile-balances":
        from aimg.scripts.reconcile import main as reconcile_main

        reconcile_main()
    else:
        print(f"Unknown command: {command}")
        print("Usage: python -m aimg <api|worker|admin|seed|sync-job-types|reconcile-balances>")
        sys.exit(1)


main()
