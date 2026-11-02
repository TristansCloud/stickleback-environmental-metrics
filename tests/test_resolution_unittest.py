import unittest

from enviro_data.lake_polygons import resolution_sensitivity


class ResolutionTests(unittest.TestCase):
    def test_rough_shore_changes_perimeter_more_than_area(self):
        outer = [(0, 0), (.004, 0), (.005, .0004), (.006, 0), (.01, 0),
                 (.01, .01), (0, .01), (0, 0)]
        rows = resolution_sensitivity([[outer]], .002, .002, (0, 60))
        self.assertEqual([r['status'] for r in rows], ['accepted', 'accepted'])
        self.assertLess(rows[1]['lake_perimeter_m'], rows[0]['lake_perimeter_m'])
        self.assertGreater(rows[1]['lake_area_perimeter_m'], rows[0]['lake_area_perimeter_m'])

    def test_reject_negative_tolerance(self):
        with self.assertRaises(ValueError):
            resolution_sensitivity([[[(0, 0), (.01, 0), (.01, .01), (0, .01), (0, 0)]]], .005, .005, (-1,))
