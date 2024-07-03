import json
import perf

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import tftbase

from host import Result
from logger import logger
from perf import PerfClient
from perf import PerfServer
from testSettings import TestSettings
from testType import TestTypeHandler
from tftbase import Bitrate
from tftbase import ConnectionMode
from tftbase import IperfOutput
from tftbase import TestType
from thread import ReturnValueThread


IPERF_EXE = "iperf3"
IPERF_UDP_OPT = "-u -b 25G"
IPERF_REV_OPT = "-R"


@dataclass(frozen=True)
class TestTypeHandlerIperf(TestTypeHandler):
    def _create_server_client(self, ts: TestSettings) -> tuple[PerfServer, PerfClient]:
        s = IperfServer(ts=ts)
        c = IperfClient(ts=ts, server=s)
        return (s, c)

    def can_run_reverse(self) -> bool:
        if self.test_type == TestType.IPERF_TCP:
            return True
        return False

    def _calculate_gbps_tcp(self, result: Mapping[str, Any]) -> Bitrate:
        try:
            sum_sent = result["end"]["sum_sent"]
            sum_received = result["end"]["sum_received"]
        except KeyError as e:
            logger.error(
                f"KeyError: {e}. Malformed results when parsing iperf tcp for sum_sent/received"
            )
            raise Exception(
                "calculate_gbps_iperf_tcp(): failed to parse iperf test results"
            )

        bitrate_sent = sum_sent["bits_per_second"] / 1e9
        bitrate_received = sum_received["bits_per_second"] / 1e9

        return Bitrate(
            tx=float(f"{bitrate_sent:.5g}"), rx=float(f"{bitrate_received:.5g}")
        )

    def _calculate_gbps_udp(self, result: Mapping[str, Any]) -> Bitrate:

        sum_data = result["end"]["sum"]

        # UDP tests only have sender traffic
        bitrate_sent = sum_data["bits_per_second"] / 1e9
        return Bitrate(tx=float(f"{bitrate_sent:.5g}"), rx=float(f"{bitrate_sent:.5g}"))

    def calculate_gbps(self, result: Mapping[str, Any]) -> Bitrate:
        # If an error occurred, bitrate = 0
        if "error" in result:
            logger.error(f"An error occurred during iperf test: {result['error']}")
            return Bitrate.NA

        if self.test_type == TestType.IPERF_TCP:
            return self._calculate_gbps_tcp(result)
        return self._calculate_gbps_udp(result)


test_type_handler_iperf_tcp = TestTypeHandlerIperf(TestType.IPERF_TCP)
test_type_handler_iperf_udp = TestTypeHandlerIperf(TestType.IPERF_UDP)


class IperfServer(perf.PerfServer):
    def __init__(self, ts: TestSettings):
        super().__init__(ts)

        self.exec_persistent = ts.conf_server.persistent

    def get_template_args(self) -> dict[str, str]:

        extra_args: dict[str, str] = {}
        if self.exec_persistent:
            extra_args["command"] = IPERF_EXE
            extra_args["args"] = f'["-s", "-p", "{self.port}"]'

        return {
            **super().get_template_args(),
            **extra_args,
        }

    def setup(self) -> None:
        cmd = f"{IPERF_EXE} -s -p {self.port} --one-off --json"
        if self.connection_mode == ConnectionMode.EXTERNAL_IP:
            cmd = f"podman run -it --init --replace --rm -p {self.port} --name={self.pod_name} {tftbase.TFT_TOOLS_IMG} {cmd}"
            cleanup_cmd = f"podman rm --force {self.pod_name}"
        else:
            # Create the server pods
            super().setup()
            cmd = f"exec {self.pod_name} -- {cmd}"
            cleanup_cmd = f"exec -t {self.pod_name} -- killall {IPERF_EXE}"

        logger.info(f"Running {cmd}")

        def server(self: IperfServer, cmd: str) -> Result:
            if self.connection_mode == ConnectionMode.EXTERNAL_IP:
                return self.lh.run(cmd)
            elif self.exec_persistent:
                return Result("Server is persistent.", "", 0)
            return self.run_oc(cmd)

        self.exec_thread = ReturnValueThread(
            target=server,
            args=(self, cmd),
            cleanup_action=server,
            cleanup_args=(self, cleanup_cmd),
        )
        self.exec_thread.start()
        self.confirm_server_alive()


class IperfClient(perf.PerfClient):
    def __init__(self, ts: TestSettings, server: IperfServer):
        super().__init__(ts, server)

    def run(self, duration: int) -> None:
        def client(self: IperfClient, cmd: str) -> Result:
            self.ts.clmo_barrier.wait()
            r = self.run_oc(cmd)
            self.ts.event_client_finished.set()
            return r

        server_ip = self.get_target_ip()
        self.cmd = f"exec {self.pod_name} -- {IPERF_EXE} -c {server_ip} -p {self.port} --json -t {duration}"
        if self.test_type == TestType.IPERF_UDP:
            self.cmd = f" {self.cmd} {IPERF_UDP_OPT}"
        if self.reverse:
            self.cmd = f" {self.cmd} {IPERF_REV_OPT}"
        self.exec_thread = ReturnValueThread(target=client, args=(self, self.cmd))
        self.exec_thread.start()

    def generate_output(self, data: str) -> IperfOutput:
        parsed_data = json.loads(data)
        json_dump = IperfOutput(
            tft_metadata=self.ts.get_test_metadata(),
            command=self.cmd,
            result=parsed_data,
        )
        return json_dump

    def output(self, out: tftbase.TftAggregateOutput) -> None:
        # Return machine-readable output to top level
        assert isinstance(
            self._output, IperfOutput
        ), f"Expected variable to be of type IperfOutput, got {type(self._output)} instead."
        out.flow_test = self._output

        # Print summary to console logs
        logger.info(f"Results of {self.ts.get_test_str()}:")
        if self.iperf_error_occurred(self._output.result):
            logger.error(
                "Encountered error while running test:\n"
                f"  {self._output.result['error']}"
            )
            return
        if self.test_type == TestType.IPERF_TCP:
            self.print_tcp_results(self._output.result)
        if self.test_type == TestType.IPERF_UDP:
            self.print_udp_results(self._output.result)

    def print_tcp_results(self, data: Mapping[str, Any]) -> None:
        sum_sent = data["end"]["sum_sent"]
        sum_received = data["end"]["sum_received"]

        transfer_sent = sum_sent["bytes"] / (1024**3)
        bitrate_sent = sum_sent["bits_per_second"] / 1e9
        transfer_received = sum_received["bytes"] / (1024**3)
        bitrate_received = sum_received["bits_per_second"] / 1e9
        mss = data["start"]["tcp_mss_default"]

        logger.info(
            f"\n  [ ID]   Interval              Transfer        Bitrate\n"
            f"  [SENT]   0.00-{sum_sent['seconds']:.2f} sec   {transfer_sent:.2f} GBytes  {bitrate_sent:.2f} Gbits/sec sender\n"
            f"  [REC]   0.00-{sum_received['seconds']:.2f} sec   {transfer_received:.2f} GBytes  {bitrate_received:.2f} Gbits/sec receiver\n"
            f"  MSS = {mss}"
        )

    def print_udp_results(self, data: Mapping[str, Any]) -> None:
        sum_data = data["end"]["sum"]

        total_gigabytes = sum_data["bytes"] / (1024**3)
        average_gigabitrate = sum_data["bits_per_second"] / 1e9
        average_jitter = sum_data["jitter_ms"]
        total_lost_packets = sum_data["lost_packets"]
        total_lost_percent = sum_data["lost_percent"]

        logger.info(
            f"\n  Total GBytes: {total_gigabytes:.4f} GBytes\n"
            f"  Average Bitrate: {average_gigabitrate:.2f} Gbits/s\n"
            f"  Average Jitter: {average_jitter:.9f} ms\n"
            f"  Total Lost Packets: {total_lost_packets}\n"
            f"  Total Lost Percent: {total_lost_percent:.2f}%"
        )

    def iperf_error_occurred(self, data: Mapping[str, Any]) -> bool:
        return "error" in data