.PHONY: up down lint format types test migrate migrate-down content-validate content-sync eval-retrieval verify

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

content-validate:
	$(MAKE) -C backend content-validate

content-sync:
	$(MAKE) -C backend content-sync

eval-retrieval:
	$(MAKE) -C backend eval-retrieval

verify:
	$(MAKE) -C backend verify
