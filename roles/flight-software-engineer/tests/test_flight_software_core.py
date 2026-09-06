#!/usr/bin/env python3
"""Test flight_software_core: the executable engine of the Flight
Software Engineer role.

Proves the role can DO its job standalone (no AeroSkills needed):
software bus message ID design (16-bit space, command band 0x0000-0x0FFF
= 4096 IDs, telemetry band 0x1000-0xFFFF = 61440 IDs, monotonic
sequence counters), component model rules and the rate-group master
clock, Liu-Layland / exact response-time scheduling, priority ceiling
blocking analysis, plan generation, and evidence-gate checks.

Real anchors are the values the bound AeroSkills leaves encode:
utilization 0.55 with response times [1.0, 3.0, 7.0] for the
(1,5),(2,10),(3,20) ms set; U_rm(2/3/4) = 0.828427 / 0.779763 /
0.756828; ceilings R1 = 3 / R2 = 2 with blocking 0.6 / 0.7 / 0.0 and
response times with blocking 1.6 / 3.7 / 7.0 ms.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "core"))
from flight_software_core import (  # noqa: E402
    allocate_msg_id, blocking_times, build_design_verification_plan,
    check_design_verification_plan, check_design_verification_plan_markdown,
    command_band_size, component_counts, edf_feasible, example_item,
    example_plan_markdown, liu_layland_bound, msg_id_band, msg_id_space_size,
    opcode_inventory, priority_ceiling, rate_group_schedule,
    render_design_verification_plan_markdown, resource_ceiling,
    response_time_with_blocking, rm_feasible, rm_response_times,
    rm_ub_feasible, rta_with_blocking_feasibility, scheduling_summary,
    telemetry_band_size, telemetry_seq_run, utilization,
    validate_component, validate_connections, validate_topology,
    worst_case_blocking,
)

# Reference process set (ms) and PCP task/lock model of the example item.
TASKS = [(1.0, 5.0), (2.0, 10.0), (3.0, 20.0)]
PCP_TASKS = {
    "ControlLaw": {"C": 1.0, "T": 5.0, "priority": 3.0},
    "Guidance": {"C": 2.0, "T": 10.0, "priority": 2.0},
    "HealthMon": {"C": 3.0, "T": 20.0, "priority": 1.0},
}
LOCKS = [
    {"resource": "attitude-state-store", "task": "ControlLaw", "cs": 0.5},
    {"resource": "attitude-state-store", "task": "HealthMon", "cs": 0.6},
    {"resource": "command-buffer", "task": "Guidance", "cs": 0.8},
    {"resource": "command-buffer", "task": "HealthMon", "cs": 0.7},
]


class TestMsgIdDesign(unittest.TestCase):
    """cFS software bus message design rules (cfs-architecture leaf)."""

    def test_16bit_space_and_band_sizes(self):
        self.assertEqual(msg_id_space_size(), 65536)
        self.assertEqual(command_band_size(), 4096)
        self.assertEqual(telemetry_band_size(), 61440)
        # 4096 + 61440 must tile the full 16-bit space
        self.assertEqual(command_band_size() + telemetry_band_size(),
                         msg_id_space_size())

    def test_band_boundaries(self):
        self.assertEqual(msg_id_band(0x0000), "command")
        self.assertEqual(msg_id_band(0x0FFF), "command")
        self.assertEqual(msg_id_band(0x1000), "telemetry")
        self.assertEqual(msg_id_band(0xFFFF), "telemetry")

    def test_classic_layout_app_tag_upper_bits(self):
        # 0x1900 = app 0x19, message 0x00 (classic cFS layout)
        self.assertEqual(allocate_msg_id(0x19, 0x00, "telemetry"), 0x1900)
        self.assertEqual(allocate_msg_id(0x01, 0x01, "command"), 0x0101)

    def test_allocate_rejects_wrong_band(self):
        with self.assertRaises(ValueError):
            allocate_msg_id(0x19, 0x00, "command")   # 0x1900 is telemetry
        with self.assertRaises(ValueError):
            allocate_msg_id(0x00, 0x00, "telemetry")  # 0x0000 is command

    def test_msg_id_validation(self):
        with self.assertRaises(ValueError):
            msg_id_band(0x10000)
        with self.assertRaises(ValueError):
            msg_id_band(-1)
        with self.assertRaises(ValueError):
            msg_id_band(1.5)
        with self.assertRaises(ValueError):
            msg_id_band(True)

    def test_telemetry_seq_monotonic_budget(self):
        run = telemetry_seq_run(2, 3)          # 2 msgs/cycle, 3 cycles
        self.assertEqual(run["count"], 6)
        self.assertEqual(run["first_seq"], 0)
        self.assertEqual(run["last_seq"], 5)
        self.assertTrue(run["monotonic"])
        self.assertEqual(telemetry_seq_run(1, 1)["count"], 1)
        with self.assertRaises(ValueError):
            telemetry_seq_run(0, 2)
        with self.assertRaises(ValueError):
            telemetry_seq_run(2, 0)


class TestSchedulingLogic(unittest.TestCase):
    """Liu-Layland / response-time scheduling (real-time-scheduling leaf)."""

    def test_utilization_anchor(self):
        self.assertAlmostEqual(utilization(TASKS), 0.55)

    def test_liu_layland_anchors(self):
        self.assertAlmostEqual(liu_layland_bound(2), 0.828427, places=5)
        self.assertAlmostEqual(liu_layland_bound(3), 0.779763, places=5)
        self.assertAlmostEqual(liu_layland_bound(4), 0.756828, places=5)
        self.assertAlmostEqual(liu_layland_bound(1), 1.0)

    def test_rm_response_times_exact(self):
        self.assertEqual(rm_response_times(TASKS), [1.0, 3.0, 7.0])

    def test_rm_and_edf_verdicts(self):
        self.assertTrue(rm_ub_feasible(TASKS))
        self.assertTrue(rm_feasible(TASKS))
        self.assertTrue(edf_feasible(TASKS))

    def test_scheduling_summary_verdict(self):
        s = scheduling_summary(TASKS)
        self.assertEqual(s["n_tasks"], 3)
        self.assertAlmostEqual(s["utilization"], 0.55)
        self.assertTrue(s["rm_ub_verdict"])
        self.assertEqual(s["rm_exact_response_times"], [1.0, 3.0, 7.0])
        self.assertTrue(s["rm_exact_feasible"])
        self.assertTrue(s["edf_feasible"])
        self.assertEqual(s["verdict"], "RM-guaranteed-by-UB")

    def test_leaf_worked_sets(self):
        # Set A: U 0.8333 above U_rm(3) but exactly RM-feasible
        s = scheduling_summary([(1, 3), (1, 4), (2, 8)])
        self.assertAlmostEqual(s["utilization"], 0.8333333333)
        self.assertFalse(s["rm_ub_verdict"])
        self.assertEqual(s["rm_exact_response_times"], [1.0, 2.0, 6.0])
        self.assertEqual(s["verdict"], "RM-exact-feasible (UB inconclusive)")
        # Set B: U > 1 -> divergence (None) -> RM-infeasible
        s = scheduling_summary([(2, 3), (2, 5), (2, 7)])
        self.assertIsNone(s["rm_exact_response_times"])
        self.assertEqual(s["verdict"], "RM-infeasible")
        self.assertFalse(s["edf_feasible"])
        # Set C: U below the bound -> guaranteed
        s = scheduling_summary([(1, 5), (1, 6), (2, 10)])
        self.assertEqual(s["verdict"], "RM-guaranteed-by-UB")

    def test_validation_rejections(self):
        for bad in ([], [(0, 5)], [(1, 0)], [(1,)], [(-1, 5)],
                    [("a", 5)]):
            with self.assertRaises(ValueError):
                utilization(bad)
        with self.assertRaises(ValueError):
            liu_layland_bound(0)
        with self.assertRaises(ValueError):
            liu_layland_bound(2.5)


class TestSharedResourceLogic(unittest.TestCase):
    """Priority ceiling blocking (shared-resource-access-control leaf)."""

    def test_ceilings_are_max_priority_of_lockers(self):
        c = priority_ceiling(PCP_TASKS, LOCKS)
        self.assertEqual(c["attitude-state-store"], 3.0)
        self.assertEqual(c["command-buffer"], 2.0)
        self.assertEqual(resource_ceiling(PCP_TASKS, LOCKS,
                                          "attitude-state-store"), 3.0)

    def test_blocking_truth_table(self):
        b = blocking_times(PCP_TASKS, LOCKS)
        self.assertAlmostEqual(b["ControlLaw"], 0.6)
        self.assertAlmostEqual(b["Guidance"], 0.7)
        self.assertAlmostEqual(b["HealthMon"], 0.0)

    def test_blocking_is_max_not_sum(self):
        # T1 (priority 3) is blocked only by T3's 0.6 ms section on the
        # store whose ceiling 3 clears priority 3 - never 0.5 + 0.6 + ...
        self.assertAlmostEqual(worst_case_blocking("ControlLaw",
                                                   PCP_TASKS, LOCKS), 0.6)

    def test_response_times_with_blocking_anchors(self):
        self.assertAlmostEqual(response_time_with_blocking(
            "ControlLaw", PCP_TASKS, LOCKS), 1.6)
        self.assertAlmostEqual(response_time_with_blocking(
            "Guidance", PCP_TASKS, LOCKS), 3.7)
        self.assertAlmostEqual(response_time_with_blocking(
            "HealthMon", PCP_TASKS, LOCKS), 7.0)

    def test_feasibility_with_blocking(self):
        r = rta_with_blocking_feasibility(PCP_TASKS, LOCKS)
        self.assertTrue(r["feasible"])
        self.assertEqual(r["response_times"]["ControlLaw"], 1.6)

    def test_empty_lock_identity(self):
        # no locks -> zero blocking and the plain response-time analysis
        r = rta_with_blocking_feasibility(PCP_TASKS, [])
        self.assertTrue(r["feasible"])
        self.assertEqual(r["response_times"]["ControlLaw"], 1.0)
        self.assertEqual(r["response_times"]["Guidance"], 3.0)
        self.assertEqual(r["response_times"]["HealthMon"], 7.0)

    def test_value_error_rejections(self):
        with self.assertRaises(ValueError):
            priority_ceiling(PCP_TASKS, [])          # empty locks
        with self.assertRaises(ValueError):
            blocking_times(PCP_TASKS, [{"resource": "r", "task": "nope",
                                        "cs": 0.1}])
        with self.assertRaises(ValueError):
            blocking_times({"T": {"C": 1.0, "T": 0.5, "priority": 1.0}},
                           [])                        # C > T
        with self.assertRaises(ValueError):
            worst_case_blocking("Ghost", PCP_TASKS, LOCKS)


class TestComponentModel(unittest.TestCase):
    """F Prime component rules and rate-group schedule."""

    def setUp(self):
        self.item = example_item()

    def test_reference_topology_is_clean(self):
        v = validate_topology(self.item.components, self.item.connections,
                              self.item.rate_groups)
        self.assertEqual(v, {"issues": [], "warnings": []})

    def test_component_counts(self):
        c = component_counts(self.item.components)
        self.assertEqual(c["total"], 6)
        self.assertEqual(c["active"], 2)
        self.assertEqual(c["queued"], 2)
        self.assertEqual(c["passive"], 2)

    def test_opcode_inventory_unique_in_range(self):
        ops = opcode_inventory(self.item.components)
        self.assertEqual([(o["component"], o["opcode"]) for o in ops],
                         [("ControlLaw", 1), ("Guidance", 2)])
        self.assertTrue(all(0x0000 <= o["opcode"] <= 0xFFFF for o in ops))

    def test_rate_group_schedule_master_clock(self):
        s = rate_group_schedule(self.item.rate_groups)
        self.assertEqual(s["base_hz"], 200.0)
        periods = [(g["name"], g["period_ticks"]) for g in s["groups"]]
        self.assertEqual(periods,
                         [("RG200", 1), ("RG100", 2), ("RG50", 4)])
        # explicit base clock recomputation
        s = rate_group_schedule(self.item.rate_groups, base_hz=400.0)
        self.assertEqual([(g["name"], g["period_ticks"])
                          for g in s["groups"]],
                         [("RG200", 2), ("RG100", 4), ("RG50", 8)])

    def test_active_needs_input_rule(self):
        issues = validate_component({"name": "A", "kind": "active",
                                     "ports": []})
        self.assertTrue(any("active components must declare at least one"
                            in i for i in issues))

    def test_passive_no_commands_rule(self):
        issues = validate_component({"name": "P", "kind": "passive",
                                     "commands": [{"name": "x",
                                                   "opcode": 1}]})
        self.assertTrue(any("must not declare commands" in i
                            for i in issues))

    def test_duplicate_opcode_rule(self):
        issues = validate_component({
            "name": "C", "kind": "active",
            "ports": [{"direction": "input", "name": "in",
                       "data_type": "U32"}],
            "commands": [{"name": "a", "opcode": 5},
                         {"name": "b", "opcode": 5}]})
        self.assertTrue(any("duplicate command opcode" in i
                            for i in issues))

    def test_connection_type_mismatch_and_self_loop(self):
        defs = [{"name": "A", "kind": "passive",
                 "ports": [{"direction": "output", "name": "o",
                            "data_type": "U32"}]},
                {"name": "B", "kind": "passive",
                 "ports": [{"direction": "input", "name": "i",
                            "data_type": "F32"}]}]
        issues = validate_connections(
            defs, [{"from": ("A", "o"), "to": ("B", "i")}])
        self.assertTrue(any("type mismatch" in i for i in issues))
        loop = [{"from": ("A", "o"), "to": ("A", "o")}]
        # A has no input port; a connection to an output must be flagged
        issues = validate_connections(defs, loop)
        self.assertTrue(any("input" in i for i in issues))


class TestPlanBuilder(unittest.TestCase):

    def test_example_model_numbers(self):
        model = build_design_verification_plan(example_item())
        self.assertEqual(model["status"], "draft-for-review")
        self.assertEqual(model["software_level"], "A")
        bus = model["bus_design"]
        self.assertEqual(bus["space_size"], 65536)
        self.assertEqual(bus["command_band_size"], 4096)
        self.assertEqual(bus["telemetry_band_size"], 61440)
        self.assertEqual(bus["total_msgs_per_frame"], 12)
        self.assertTrue(all(e["band_ok"] for e in bus["catalog"]))
        sc = model["scheduling"]
        self.assertAlmostEqual(sc["utilization"], 0.55)
        self.assertEqual(sc["rm_exact_response_times"], [1.0, 3.0, 7.0])
        self.assertEqual(sc["verdict"], "RM-guaranteed-by-UB")
        rc = model["resources"]
        self.assertEqual(rc["ceilings"]["attitude-state-store"], 3.0)
        self.assertEqual(rc["response_times"]["Guidance"], 3.7)
        self.assertTrue(rc["feasible"])
        cm = model["component_model"]
        self.assertEqual(cm["topology_issues"], 0)
        self.assertEqual(cm["schedule"]["base_hz"], 200.0)

    def test_example_markdown_sections_and_markers(self):
        md = example_plan_markdown()
        for sec in ["## 1. Item and software architecture",
                    "## 2. Component design model and dispatch schedule",
                    "## 3. Software bus command and telemetry design",
                    "## 4. Process scheduling analysis",
                    "## 5. Shared-resource access control design",
                    "## 6. Verification plan",
                    "## 7. Open items and sign-off"]:
            self.assertIn(sec, md)
        self.assertIn("not an approval", md.lower())
        self.assertIn("draft", md.lower())
        self.assertNotIn("___", md)

    def test_core_gates_all_pass(self):
        model = build_design_verification_plan(example_item())
        gates = check_design_verification_plan(model)
        self.assertTrue(gates["all_pass"], gates)

    def test_markdown_gates_all_pass(self):
        gates = check_design_verification_plan_markdown(
            example_plan_markdown())
        self.assertTrue(gates["all_pass"], gates)

    def test_level_gate_matches_and_rejects(self):
        md = example_plan_markdown()
        self.assertTrue(
            check_design_verification_plan_markdown(md, "A")["level_matches"])
        self.assertFalse(
            check_design_verification_plan_markdown(md, "B")["level_matches"])

    def test_unfeasible_process_set_flips_scheduling_gate(self):
        item = example_item()
        item.processes = [{"name": "A", "C_ms": 9.0, "T_ms": 10.0},
                          {"name": "B", "C_ms": 9.0, "T_ms": 10.0},
                          {"name": "C", "C_ms": 9.0, "T_ms": 10.0}]
        model = build_design_verification_plan(item)
        gates = check_design_verification_plan(model)
        self.assertFalse(gates["scheduling_numbers_present"])
        self.assertFalse(gates["all_pass"])

    def test_dirty_topology_flips_component_gate(self):
        item = example_item()
        item.connections.append({"from": ("ControlLaw", "cmdOut"),
                                 "to": ("TelemetryMux", "tlmCtrlIn")})
        # tlmCtrlIn now has two incoming connections: double dispatch
        model = build_design_verification_plan(item)
        gates = check_design_verification_plan(model)
        self.assertGreater(model["component_model"]["topology_issues"], 0)
        self.assertFalse(gates["component_model_clean"])

    def test_standalone_no_skills_repo(self):
        os.environ["AEROSKILLS_DEV"] = "/nonexistent"
        model = build_design_verification_plan(example_item())
        self.assertEqual(model["software_level"], "A")
        md = render_design_verification_plan_markdown(model)
        self.assertGreater(len(md), 3000)


if __name__ == "__main__":
    unittest.main()
