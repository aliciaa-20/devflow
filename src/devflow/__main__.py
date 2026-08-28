from devflow.config import Config


def main() -> None:
    config = Config()
    print(f"DevFlow {config.version}")
    print("Ready.")
    print()
    print("Provide a public GitHub repository URL and a change description to begin.")
    print("  Phase 1 (Repository + Change Input) is not yet implemented.")


if __name__ == "__main__":
    main()
