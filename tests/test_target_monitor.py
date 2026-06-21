from runwatch.targets import ResolvedTarget, TargetMonitor, TargetSnapshot, TargetSpec


class FakeResolver:
    def resolve(self, _spec: TargetSpec) -> ResolvedTarget:
        return ResolvedTarget(
            name="worker",
            kind="process",
            selector="worker",
            manager="none",
            main_pid=10,
            pids=(10,),
        )


class FakeSampler:
    def __init__(self) -> None:
        self.calls = 0

    def sample(self, target: ResolvedTarget) -> TargetSnapshot:
        self.calls += 1
        return TargetSnapshot(
            observed_at=float(self.calls),
            target=target,
            process_count=1,
            thread_count=2,
            cpu_time_seconds=float(self.calls),
            memory_bytes=1024,
            io_read_bytes=100 * self.calls,
            io_write_bytes=50 * self.calls,
            file_descriptors=8,
            open_regular_files=3,
        )


def test_target_monitor_calculates_rates_between_samples() -> None:
    monitor = TargetMonitor(
        TargetSpec(name="worker", kind="process", value="worker"),
        FakeResolver(),
        FakeSampler(),
    )

    first = monitor.run()
    second = monitor.run()
    samples = {sample.name: sample.value for sample in second.metrics}

    assert first.status == "ok"
    assert samples["runwatch_target_cpu_usage_cores"] == 1.0
    assert samples["runwatch_target_io_read_bytes_per_second"] == 100.0
    assert samples["runwatch_target_io_write_bytes_per_second"] == 50.0
    assert samples["runwatch_target_file_descriptors"] == 8.0
    assert samples["runwatch_target_open_regular_files"] == 3.0
    assert samples["runwatch_target_unix_sockets"] == 0.0
    assert samples["runwatch_target_unix_sockets_named"] == 0.0
    assert samples["runwatch_target_unix_sockets_unnamed"] == 0.0
    assert samples["runwatch_target_unique_remote_peers"] == 0.0
    assert second.details["network_bytes"] is None


class MissingResolver:
    def resolve(self, _spec: TargetSpec) -> ResolvedTarget:
        from runwatch.targets import TargetResolutionError

        raise TargetResolutionError("missing")


def test_missing_target_resets_target_up_metric() -> None:
    monitor = TargetMonitor(
        TargetSpec(name="missing", kind="process", value="missing"),
        MissingResolver(),
        FakeSampler(),
    )

    result = monitor.run()
    samples = {sample.name: sample.value for sample in result.metrics}

    assert result.status == "fail"
    assert samples["runwatch_target_up"] == 0.0
    assert samples["runwatch_target_processes"] == 0.0
    assert samples["runwatch_target_unix_sockets"] == 0.0
    assert samples["runwatch_target_unix_sockets_named"] == 0.0
    assert samples["runwatch_target_unix_sockets_unnamed"] == 0.0
    assert samples["runwatch_target_unique_remote_peers"] == 0.0


class PartialSampler:
    def sample(self, target: ResolvedTarget) -> TargetSnapshot:
        from runwatch.targets import CollectionCoverage

        return TargetSnapshot(
            observed_at=1.0,
            target=target,
            process_count=2,
            thread_count=4,
            cpu_time_seconds=1.0,
            memory_bytes=2048,
            io_read_bytes=0,
            io_write_bytes=0,
            file_descriptors=12,
            open_regular_files=3,
            coverage=CollectionCoverage(
                total_processes=2,
                cpu_visible=2,
                memory_visible=2,
                io_visible=2,
                threads_visible=2,
                file_descriptors_visible=2,
                open_regular_files_visible=1,
                internet_sockets_visible=1,
                unix_sockets_visible=1,
            ),
            errors=(
                "PID 11 regular files: AccessDenied",
                "PID 11 TCP/UDP sockets: AccessDenied",
            ),
        )


def test_partial_visibility_does_not_make_a_healthy_target_warn() -> None:
    monitor = TargetMonitor(
        TargetSpec(name="worker", kind="process", value="worker"),
        FakeResolver(),
        PartialSampler(),
    )

    result = monitor.run()
    samples = {sample.name: sample.value for sample in result.metrics}

    assert result.status == "ok"
    assert result.details["visibility"] == "partial"
    assert samples["runwatch_target_up"] == 1.0
    assert samples["runwatch_target_visibility_complete"] == 0.0
