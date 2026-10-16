.PHONY: up down lint format types test migrate migrate-down verify

up:
	$(MAKE) -C backend up

down:
	$(MAKE) -C backend down

lint:
	$(MAKE) -C backend lint

format:
	$(MAKE) -C backend format

types:
	$(MAKE) -C backend types

test:
	$(MAKE) -C backend test

migrate:
	$(MAKE) -C backend migrate

migrate-down:
	$(MAKE) -C backend migrate-down

verify:
	$(MAKE) -C backend verify
