"""
Test runner that tolerates Supabase's connection pooler.

On Supabase the database sits behind Supavisor (the pooler), which keeps its
server-side session open for a moment after Django disconnects. Django then
issues ``DROP DATABASE test_postgres`` against the maintenance database and
fails with:

    OperationalError: database "test_postgres" is being accessed by other users
    DETAIL:  There is 1 other session using the database.

The tests themselves have already passed at that point - only the cleanup
fails, which still makes ``manage.py test`` exit non-zero. This runner retries
the drop with ``WITH (FORCE)``, which terminates the straggler session first
(PostgreSQL 13+).
"""

import psycopg
from django.db.utils import OperationalError
from django.test.runner import DiscoverRunner
from django.test.utils import teardown_databases as _teardown_databases

POOLER_MESSAGE = "is being accessed by other users"


class PoolerSafeTestRunner(DiscoverRunner):
    """DiscoverRunner whose teardown survives a lingering pooler session."""

    def teardown_databases(self, old_config, **kwargs):
        try:
            _teardown_databases(
                old_config,
                verbosity=self.verbosity,
                parallel=self.parallel,
                keepdb=self.keepdb,
            )
        except OperationalError as exc:
            if POOLER_MESSAGE not in str(exc):
                raise
            self._force_drop_test_databases(old_config)

    def _force_drop_test_databases(self, old_config) -> None:
        for connection, _old_name, destroy in old_config:
            if not destroy or connection.vendor != "postgresql":
                continue
            # During teardown settings_dict["NAME"] is the TEST database name
            # (this mirrors Django's own destroy_test_db). The `old_name` from
            # old_config is the *original* database - dropping that would take
            # out the real database, so it must never be used here.
            test_db_name = connection.settings_dict["NAME"]
            if not test_db_name or test_db_name in {"postgres", "template1", "template0"}:
                raise RuntimeError(
                    f"Refusing to force-drop {test_db_name!r} - that is not a test database."
                )
            params = connection.get_connection_params()
            params["dbname"] = "postgres"  # maintenance database
            with psycopg.connect(**params, autocommit=True) as maintenance:
                maintenance.execute(
                    f'DROP DATABASE IF EXISTS "{test_db_name}" WITH (FORCE)'
                )
            print(f"Destroyed test database for alias '{connection.alias}' (forced).")
