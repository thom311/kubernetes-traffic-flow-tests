import os
import pytest
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ktoolbox import common  # noqa: E402

import tftbase  # noqa: E402

from tftbase import FlowTestOutput  # noqa: E402
from tftbase import PodInfo  # noqa: E402
from tftbase import PodType  # noqa: E402
from tftbase import TestCaseTypInfo  # noqa: E402
from tftbase import TestCaseType  # noqa: E402
from tftbase import TestMetadata  # noqa: E402
from tftbase import TestType  # noqa: E402


def test_pod_info() -> None:
    pod = PodInfo(name="test_pod", pod_type=PodType.NORMAL, is_tenant=True, index=0)
    assert pod.name == "test_pod"
    assert pod.pod_type == PodType.NORMAL
    assert pod.is_tenant is True
    assert pod.index == 0


def test_test_metadata() -> None:
    server = PodInfo(
        name="server_pod", pod_type=PodType.NORMAL, is_tenant=True, index=0
    )
    client = PodInfo(
        name="client_pod", pod_type=PodType.NORMAL, is_tenant=False, index=1
    )
    metadata = TestMetadata(
        tft_idx=0,
        test_cases_idx=0,
        connections_idx=0,
        reverse=False,
        test_case_id=TestCaseType.POD_TO_POD_SAME_NODE,
        test_type=TestType.IPERF_TCP,
        server=server,
        client=client,
    )
    assert metadata.reverse is False
    assert metadata.test_case_id == TestCaseType.POD_TO_POD_SAME_NODE
    assert metadata.test_type == TestType.IPERF_TCP
    assert metadata.server == server
    assert metadata.client == client


def test_iperf_output() -> None:
    server = PodInfo(
        name="server_pod", pod_type=PodType.NORMAL, is_tenant=True, index=0
    )
    client = PodInfo(
        name="client_pod", pod_type=PodType.NORMAL, is_tenant=False, index=1
    )
    metadata = TestMetadata(
        tft_idx=0,
        test_cases_idx=0,
        connections_idx=0,
        reverse=False,
        test_case_id=TestCaseType.POD_TO_POD_SAME_NODE,
        test_type=TestType.IPERF_TCP,
        server=server,
        client=client,
    )
    FlowTestOutput(
        command="command",
        result={},
        tft_metadata=metadata,
        bitrate_gbps=tftbase.Bitrate.NA,
    )

    common.dataclass_from_dict(
        FlowTestOutput,
        {
            "command": "command",
            "result": {},
            "tft_metadata": metadata,
            "bitrate_gbps": {"tx": 0.0, "rx": 0.0},
        },
    )

    o = common.dataclass_from_dict(
        FlowTestOutput,
        {
            "command": "command",
            "result": {},
            "tft_metadata": metadata,
            "bitrate_gbps": {"tx": None, "rx": 0},
        },
    )
    assert o.bitrate_gbps.tx is None
    assert o.bitrate_gbps.rx == 0.0

    with pytest.raises(ValueError):
        common.dataclass_from_dict(
            FlowTestOutput,
            {
                "command": "command",
                "result": {},
                "tft_metadata": metadata,
            },
        )
    with pytest.raises(TypeError):
        common.dataclass_from_dict(
            FlowTestOutput,
            {
                "command": "command",
                "result": {},
                "tft_metadata": "string",
                "bitrate_gbps": {"tx": 0.0, "rx": 0.0},
            },
        )


def test_test_case_typ_infos() -> None:
    for typ, ti in tftbase._test_case_typ_infos.items():
        assert typ == ti.test_case_type
    assert list(tftbase._test_case_typ_infos) == list(TestCaseType)
    test_case_typ_infos = list(tftbase._test_case_typ_infos.values())
    assert list(tftbase._test_case_typ_infos) == [
        ti.test_case_type for ti in test_case_typ_infos
    ]
    for typ, ti in tftbase._test_case_typ_infos.items():
        assert ti.test_case_type is typ
        assert typ.info is ti

    assert list(TestCaseType)[-1].value == 29
    list_numeric = list(range(1, list(TestCaseType)[-1].value + 1))
    list_numeric = [x for x in list_numeric if x not in (11, 12, 13, 14, 26)]
    assert list_numeric == [typ.value for typ in tftbase.TestCaseType]

    def _is_identical(ti1: TestCaseTypInfo, ti2: TestCaseTypInfo) -> bool:
        assert ti1.test_case_type != ti2.test_case_type
        return (
            ti1.connection_mode == ti2.connection_mode
            and ti1.is_same_node == ti2.is_same_node
            and ti1.is_server_hostbacked == ti2.is_server_hostbacked
            and ti1.is_client_hostbacked == ti2.is_client_hostbacked
        )

    for idx1, ti1 in enumerate(test_case_typ_infos):
        for idx2, ti2 in enumerate(test_case_typ_infos[idx1 + 1 :]):
            assert not _is_identical(ti1, ti2)
    for idx1, ti1 in enumerate(test_case_typ_infos):
        assert (
            ti1.test_case_type == (list(TestCaseType))[idx1]
        ), 'We expect that "_test_case_typ_infos" follows the same order as the values in the enum'


def test_eval_binary_opt_in() -> None:

    assert tftbase.eval_binary_opt_in(None, None) == (True, True)

    assert tftbase.eval_binary_opt_in(False, None) == (False, True)
    assert tftbase.eval_binary_opt_in(None, False) == (True, False)
    assert tftbase.eval_binary_opt_in(True, None) == (True, False)
    assert tftbase.eval_binary_opt_in(None, True) == (False, True)

    assert tftbase.eval_binary_opt_in(False, False) == (False, False)
    assert tftbase.eval_binary_opt_in(True, True) == (True, True)

    assert tftbase.eval_binary_opt_in(True, False) == (True, False)
    assert tftbase.eval_binary_opt_in(False, True) == (False, True)


def test_tftfile() -> None:
    f = tftbase.tftfile("manifests/host-pod.yaml.j2")
    assert f == tftbase.tftfile("manifests", "host-pod.yaml.j2")
    assert f == tftbase.tftfile("manifests", "./host-pod.yaml.j2")
    assert os.path.exists(f)
    assert f.endswith("/manifests/host-pod.yaml.j2")


def test_get_manifest() -> None:
    if os.getenv(tftbase.ENV_TFT_MANIFESTS_OVERRIDES):
        return

    f = tftbase.get_manifest("host-pod.yaml.j2")
    assert f in (
        tftbase.tftfile("manifests/host-pod.yaml.j2"),
        tftbase.tftfile("manifests/overrides/host-pod.yaml.j2"),
    )
    assert os.path.exists(f)


def test_str_sanitize() -> None:
    assert tftbase.str_sanitize("") == ""
    assert tftbase.str_sanitize("hello!wo_rld@12.3") == "hello_21_wo__rld_40_12_o3"
