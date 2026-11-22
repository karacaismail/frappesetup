"""Synthetic accounts shared by the fixture server and the load client."""

LOAD_ACCOUNTS = {
	f"Bearer fixture-load-{number}": f"mobile-load-{number}@example.test" for number in range(1, 11)
}
