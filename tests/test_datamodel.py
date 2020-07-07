#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2013-2020 European Commission (JRC);
# Licensed under the EUPL (the 'Licence');
# You may not use this work except in compliance with the Licence.
# You may obtain a copy of the Licence at: http://ec.europa.eu/idabc/eupl

import functools as fnt
import itertools as itt

import pandas as pd

from graphtik import compose
from wltp import cycles, datamodel
from wltp import io as wio
from wltp.experiment import Experiment

from .goodvehicle import goodVehicle
from .vehdb import oneliner


def testGoodVehicle():
    mdl = goodVehicle()

    exp = Experiment(mdl)
    mdl = exp._model
    defwot = datamodel.upd_default_load_curve({})["wot"]
    assert pd.DataFrame(mdl["wot"][["n_norm", "p_norm"]]).equals(pd.DataFrame(defwot))


def testOverlayOnInit():
    mdl = goodVehicle()
    n_rated = 6000
    mdl2 = {"n_rated": n_rated}

    exp = Experiment(datamodel.merge(mdl, mdl2))
    mdl = exp._model
    assert mdl["n_rated"] == n_rated


def test_get_class_parts_limits_sorted():
    classes = datamodel.get_wltc_data()["classes"]
    class_limits = {
        cls: datamodel.get_class_parts_limits(cls, edges=True) for cls in classes.keys()
    }
    for (cls, l) in class_limits.items():
        assert l == tuple(sorted(l)), f"Class({cls}): Unsorted!"


def test_get_class_parts_limits_with_edges():
    classes = datamodel.get_wltc_data()["classes"]
    class_limits = {
        cls: datamodel.get_class_parts_limits(cls, edges=True) for cls in classes.keys()
    }
    for (cls, l) in class_limits.items():
        assert l[0] == 0, f"Class({cls}): Left-edge not 0!"
    for (cls, l) in class_limits.items():
        assert l[-1] == len(
            classes[cls]["V_cycle"]
        ), f"Class({cls}): Section Right-edge not len(cycle)!"


def test_get_class_pmr_limits():
    l = datamodel.get_class_pmr_limits()
    assert l == [22, 34]


def test_get_class_pmr_limits_with_edges():
    pmr_limits = datamodel.get_class_pmr_limits(edges=True)
    assert pmr_limits[0] == 0, "Left-edge not 0!"
    assert pmr_limits[-1] == float("inf"), "PMR-limit: Right-edge not INF!"


def test_get_class_part_boundaries():
    wcd = datamodel.get_wltc_data()
    cd = cycles.get_wltc_class_data(wcd, 3)
    pmr_boundaries = cycles.get_class_part_boundaries(cd["lengths"], cd["V_cycle"])
    assert len(pmr_boundaries) == 4
    assert pmr_boundaries[0][0] == 0
    assert pmr_boundaries[-1][-1] == 1801
    nums = tuple(itt.chain(*pmr_boundaries))
    assert tuple(sorted(nums)) == nums


def test_calc_class_part_distances():
    aug = wio.make_autograph()
    funcs = [
        cycles.get_wltc_class_data,
        cycles.get_class_part_boundaries,
        cycles.calc_class_part_distances,
    ]
    ops = [aug.wrap_fn(fn) for fn in funcs]
    pipe = compose("dist", *ops)
    inp = {"wltc_data": datamodel.get_wltc_data(), "wltc_class": "class3b"}
    sol = pipe.compute(inp)
    got = sol["class_part_distances"]
    print(got)
    assert oneliner(got) == oneliner(
        """
        [0, 590)        11140.3
        [590, 1023)     17121.2
        [1023, 1478)    25782.2
        [1478, 1801)    29714.9
        Name: V_cycle, dtype: float64
    """
    )
