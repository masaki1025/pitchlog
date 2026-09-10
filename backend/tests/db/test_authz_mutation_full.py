"""資産由来の全 mutation を実 PostgreSQL へ適用して判定する。"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass

import pytest

from .authz.mutation import (
    MutationCluster,
    MutationRunner,
    PsycopgMutationIsolationProvider,
    load_mutation_catalog,
)
from .authz.mutation_execution import (
    FullMutationExecutor,
    mutation_filters_from_environment,
    run_mutation_batches,
    select_mutation_batches,
)
from .conftest import DisposablePostgres

pytestmark = pytest.mark.requires_db


@dataclass(slots=True)
class _MutationClusterAdapter:
    """Readonly fixture 値を Step 17 の可変 protocol へ写像する。"""

    container_name: str
    admin_dsn: str


def _cluster_adapter(cluster: DisposablePostgres) -> _MutationClusterAdapter:
    """使い捨てクラスタからランナーが使う 2 属性だけを返す。"""
    return _MutationClusterAdapter(
        container_name=cluster.container_name,
        admin_dsn=cluster.admin_dsn,
    )


def _adapted_cluster_factory(
    factory: Callable[[], AbstractContextManager[DisposablePostgres]],
) -> Callable[[], AbstractContextManager[MutationCluster]]:
    """既存 Docker fixture を Step 17 の factory protocol へ適合させる。"""

    @contextmanager
    def adapted() -> Iterator[MutationCluster]:
        """新しいクラスタを必要な 2 属性だけで公開する。"""
        with factory() as cluster:
            yield _cluster_adapter(cluster)

    return adapted


def test_all_asset_mutations_are_killed_without_automatic_equivalence_exclusion(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
) -> None:
    """選択した全 mutation を新 DB で実行し、非 kill を機械可読に報告する。"""
    catalog = load_mutation_catalog()
    axis, operator_id = mutation_filters_from_environment(os.environ)
    batches = select_mutation_batches(
        catalog,
        axis=axis,
        operator_id=operator_id,
    )

    # 共有クラスタ対象もテストセッション外へ状態を残さない。変異ごとの
    # cluster_is_fresh は False のままなので、KILL-05 の区別は維持される。
    with disposable_postgres_cluster() as shared_cluster:
        isolation = PsycopgMutationIsolationProvider(
            _cluster_adapter(shared_cluster),
            _adapted_cluster_factory(disposable_postgres_cluster),
        )
        runner = MutationRunner(catalog, isolation)
        executor = FullMutationExecutor(catalog)

        verdicts = run_mutation_batches(runner, executor, batches)

    selected_ids = frozenset(
        mutant_id for batch in batches for mutant_id in batch.mutant_ids
    )
    assert frozenset(verdict.mutant_id for verdict in verdicts) == selected_ids
    assert all(verdict.accepted for verdict in verdicts)
