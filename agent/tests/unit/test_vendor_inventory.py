"""Vendor inventory: schema, honesty about gaps, and the licensing refusal.

Two properties matter more than the schema checks.

First, a vendor with nothing public must say so. An inventory where Apple is
simply absent reads as complete, and a coverage report built on it overstates
what AUTON can check.

Second, non-redistributable documents must not be fetchable into a tracked
path. Most silicon specs are freely downloadable and not freely
redistributable; that is easy to violate once ingestion is automated and
tedious to undo afterwards, so it is a refusal rather than a guideline.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from vendor_inventory import (  # noqa: E402
    INVENTORY,
    InventoryError,
    coverage,
    fetch_plan,
    is_tracked_path,
    load,
)


@pytest.fixture(scope="module")
def vendors():
    return load()


@pytest.fixture
def inventory_file(tmp_path):
    """Write a one-vendor inventory with fields overridden."""
    def _write(**overrides):
        vendor = {
            "vendor": "acme",
            "category": "cpu",
            "identity_keys": ["family"],
            "documents": [{
                "id": "acme-manual",
                "title": "ACME Manual",
                "kind": "architecture-manual",
                "access": "public-download",
                "redistributable": False,
                "form": "pdf",
            }],
        }
        for k, v in overrides.items():
            if k.startswith("doc_"):
                field = k[4:]
                if v is None:
                    vendor["documents"][0].pop(field, None)
                else:
                    vendor["documents"][0][field] = v
            elif v is None:
                vendor.pop(k, None)
            else:
                vendor[k] = v
        p = tmp_path / "vendors.yaml"
        p.write_text(yaml.safe_dump({"version": 1, "vendors": [vendor]}))
        return p
    return _write


class TestTheShippedInventory:
    def test_it_loads(self, vendors):
        assert len(vendors) >= 20

    def test_every_vendor_from_the_prd_landscape_is_present(self, vendors):
        names = {v.vendor for v in vendors}
        expected = {
            "intel", "amd", "arm", "riscv-international", "ibm-openpower",
            "sifive", "loongson",                                   # cpu/isa
            "intel-gpu", "amd-gpu", "nvidia",                       # gpu
            "ti", "nxp", "st", "microchip", "broadcom-rpi",
            "rockchip", "allwinner", "qualcomm", "apple",           # soc
            "uefi-forum", "usb-if", "pci-sig", "nvm-express",
            "bluetooth-sig", "jedec", "mipi", "sd-association", "ieee-802",
        }
        assert expected <= names, f"missing: {sorted(expected - names)}"

    def test_vendors_with_nothing_public_say_so(self, vendors):
        """Silence reads as coverage. Apple, Qualcomm and MIPI publish nothing
        ingestible and must carry that as a record, not an omission."""
        for name in ("apple", "qualcomm", "mipi"):
            v = next(x for x in vendors if x.vendor == name)
            assert not v.documents
            assert v.gaps, f"{name} has no documents and no stated gap"
            assert all(g["reason"].strip() for g in v.gaps)

    def test_every_vendor_declares_how_its_errata_are_keyed(self, vendors):
        """Without identity_keys an erratum matches a vendor, not a machine."""
        for v in vendors:
            assert v.identity_keys, v.vendor

    def test_x86_vendors_key_on_the_cpuid_fields(self, vendors):
        """family/model/stepping is the join column CPUID leaf 1 provides, and
        the reason x86 conformance checking is tractable at all."""
        for name in ("intel", "amd"):
            v = next(x for x in vendors if x.vendor == name)
            assert {"family", "model", "stepping"} <= set(v.identity_keys)

    def test_the_schema_covers_four_shapes_without_extra_fields(self, vendors):
        """Intel (four kinds, three forms, four cadences), Arm (per-core),
        RISC-V (open, no central errata) and a standards body. A schema
        designed against RISC-V alone would have broken on Intel."""
        shapes = [v for v in vendors
                  if v.vendor in ("intel", "arm", "riscv-international", "pci-sig")]
        assert len(shapes) == 4
        fields = {frozenset(vars(v)) for v in shapes}
        assert len(fields) == 1, "a shape needed a field the others lack"

    def test_redistributable_documents_name_a_licence(self, vendors):
        for v in vendors:
            for d in v.documents:
                if d.redistributable:
                    assert d.licence, f"{v.vendor}/{d.id}"

    def test_no_vendor_document_is_committed(self):
        """The rule, checked against the repo rather than asserted in prose."""
        import subprocess
        out = subprocess.run(["git", "ls-files"], cwd=ROOT,
                             capture_output=True, text=True).stdout
        pdfs = [f for f in out.splitlines() if f.lower().endswith(".pdf")]
        assert not pdfs, f"vendor documents committed: {pdfs[:5]}"


class TestTheLicensingRefusal:
    def test_a_tracked_destination_is_refused(self):
        with pytest.raises(InventoryError, match="refusing to plan a fetch"):
            fetch_plan("intel", "agent/hardware/docs")

    def test_the_refusal_names_the_blocking_documents(self):
        with pytest.raises(InventoryError) as exc:
            fetch_plan("intel", "agent/hardware/docs")

        assert "intel-sdm" in str(exc.value)
        assert "never vendor the source" in str(exc.value)

    def test_an_untracked_cache_is_allowed(self):
        plan = fetch_plan("intel", ".cache/vendor")

        assert len(plan) == 10       # 4 kinds, plus 6 H9 lineage spec updates
        assert all(p["into"].startswith(".cache/vendor/intel") for p in plan)

    def test_a_traversal_out_of_the_cache_is_still_caught(self):
        """`.cache/../agent` is a tracked path wearing a disguise, which is why
        the check resolves the destination rather than matching a prefix."""
        with pytest.raises(InventoryError, match="refusing"):
            fetch_plan("intel", ".cache/vendor/../../agent/hardware")

    def test_redistributable_only_vendors_may_target_a_tracked_path(self):
        """RISC-V's specs are CC-BY, so there is nothing to refuse. The rule is
        about the licence, not about caution in general."""
        plan = fetch_plan("riscv-international", "agent/hardware/derived")

        assert len(plan) == 2

    @pytest.mark.parametrize("path,tracked", [
        ("agent/hardware", True),
        ("SLM/datasets", True),
        ("tests/kernel", True),
        (".cache/vendor", False),
        ("/tmp/whatever", False),
    ])
    def test_tracked_path_detection(self, path, tracked):
        assert is_tracked_path(path) is tracked

    def test_a_vendor_with_no_documents_cannot_be_fetched(self):
        with pytest.raises(InventoryError, match="no documents to fetch"):
            fetch_plan("apple", ".cache/vendor")

    def test_an_unknown_vendor_is_rejected_with_the_known_list(self):
        with pytest.raises(InventoryError, match="unknown vendor"):
            fetch_plan("cyberdyne", ".cache/vendor")


class TestSchemaValidation:
    @pytest.mark.parametrize("field", ["vendor", "category", "identity_keys"])
    def test_a_missing_vendor_field_is_named(self, inventory_file, field):
        with pytest.raises(InventoryError, match=field):
            load(inventory_file(**{field: None}))

    @pytest.mark.parametrize("field", ["id", "title", "kind", "access", "form"])
    def test_a_missing_document_field_is_named(self, inventory_file, field):
        with pytest.raises(InventoryError, match=field):
            load(inventory_file(**{f"doc_{field}": None}))

    def test_an_unknown_access_level_is_rejected(self, inventory_file):
        with pytest.raises(InventoryError, match="access"):
            load(inventory_file(doc_access="ask-nicely"))

    def test_an_unknown_category_is_rejected(self, inventory_file):
        with pytest.raises(InventoryError, match="category"):
            load(inventory_file(category="wetware"))

    def test_empty_identity_keys_are_rejected(self, inventory_file):
        with pytest.raises(InventoryError, match="identity_keys is empty"):
            load(inventory_file(identity_keys=[]))

    def test_a_non_boolean_redistributable_is_rejected(self, inventory_file):
        """'probably' is how a licensing violation gets committed."""
        with pytest.raises(InventoryError, match="must be true or false"):
            load(inventory_file(doc_redistributable="probably"))

    def test_redistributable_without_a_licence_is_rejected(self, inventory_file):
        with pytest.raises(InventoryError, match="no licence is named"):
            load(inventory_file(doc_redistributable=True))

    def test_a_vendor_with_neither_documents_nor_gaps_is_rejected(self, inventory_file):
        with pytest.raises(InventoryError, match="no documents and no gaps"):
            load(inventory_file(documents=[]))

    def test_a_gap_without_a_reason_is_rejected(self, inventory_file):
        with pytest.raises(InventoryError, match="'kind' and 'reason'"):
            load(inventory_file(documents=[], gaps=[{"kind": "errata"}]))

    def test_a_duplicate_document_id_is_rejected(self, tmp_path):
        p = tmp_path / "dupes.yaml"
        doc = {"id": "same", "title": "T", "kind": "errata",
               "access": "public-web", "redistributable": False, "form": "pdf"}
        p.write_text(yaml.safe_dump({"vendors": [
            {"vendor": "a", "category": "cpu", "identity_keys": ["f"], "documents": [doc]},
            {"vendor": "b", "category": "cpu", "identity_keys": ["f"], "documents": [dict(doc)]},
        ]}))
        with pytest.raises(InventoryError, match="appears twice"):
            load(p)


class TestCoverageReporting:
    def test_it_separates_inventoried_from_ingested(self, vendors):
        """The PRD's metric counts ingestion pipelines. Reporting the inventory
        count against that target would overstate progress by all of the
        remaining work."""
        report = coverage(vendors)

        assert "INVENTORIED IS NOT INGESTED" in report
        assert "ingested    : 0 vendors" in report

    def test_it_names_vendors_with_nothing_available(self, vendors):
        report = coverage(vendors)

        assert "apple" in report and "qualcomm" in report and "mipi" in report

    def test_it_reports_which_vendors_publish_errata(self, vendors):
        report = coverage(vendors)

        assert "with errata docs" in report
        assert "intel" in report and "arm" in report
