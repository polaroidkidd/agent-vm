.PHONY: test check

test:
	PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests -v

check: test
	/usr/bin/python3 -m compileall -q src tests
	git diff --check
