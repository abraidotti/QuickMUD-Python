import unittest

from charm_tools.explore import checks
from charm_tools.explore.areafile import graph
from charm_tools.explore.areafile.world import load_world


class ChecksTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = load_world()
        cls.results = {r.id: r for r in checks.run(cls.world)}

    def test_stock_world_boots_with_its_four_warnings(self):
        self.assertTrue(self.results["boot.fatal"].clean)
        self.assertEqual(len(self.results["boot.bug"].occurrences), 4)

    def test_proto_is_unlisted(self):
        self.assertEqual([o.what for o in self.results["area.unlisted"].occurrences], ["proto.are"])

    def test_pet_shop_storage_isnt_reported_unreachable(self):
        unreachable = {o.what.split()[0] for o in self.results["room.unreachable"].occurrences}
        self.assertNotIn("#3032", unreachable)  # Midgaard's pet shop storage, the room after 3031

    def test_code_created_objects_arent_reported(self):
        never = {int(o.what.split()[0][1:]) for o in self.results["obj.never-placed"].occurrences}
        self.assertNotIn(3701, never)  # OBJ_VNUM_SCHOOL_DAGGER: handed out by the game, not by a reset

    def test_every_check_says_what_it_cant_see_when_that_matters(self):
        for rid in ("mob.never-spawns", "obj.never-placed", "room.unreachable"):
            self.assertTrue(self.results[rid].not_checked, rid)

    def test_temple_reaches_the_school(self):
        self.assertIn(3700, graph.reachable(self.world, 3001))


if __name__ == "__main__":
    unittest.main()
