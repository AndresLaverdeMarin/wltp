#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2013-2019 European Commission (JRC);
# Licensed under the EUPL (the 'Licence');
# You may not use this work except in compliance with the Licence.
# You may obtain a copy of the Licence at: http://ec.europa.eu/idabc/eupl
"""formulae for cyle/vehicle dynamics"""
import dataclasses
import itertools as itt
import logging
from numbers import Number
from typing import Iterable, List
from typing import Sequence as Seq
from typing import Union

import numpy as np
import pandas as pd
from jsonschema import ValidationError
from pandas.core.generic import NDFrame
from toolz import itertoolz as itz

from . import io as wio
from .engine import NMinDrives

Column = Union[NDFrame, np.ndarray, Number]
log = logging.getLogger(__name__)


def calc_acceleration(V: Column) -> np.ndarray:
    """
    Acordign to formula in Annex 2-3.1

    :return:
        in m/s^2

        .. Attention::
            the result in the last sample is NAN!

    """
    A = np.diff(V) / 3.6
    A = np.append(A, np.NAN)  # Restore element lost by diff().
    # Panda code same with the above: ``(-V.diff(-1))```

    return A


class CycleBuilder:
    ## Default `safety_margin` redundant here, but facilitates test code.
    SM: float = 0.1
    multi_column_separator: str = "."

    #: The instance that is built.
    cycle: pd.DataFrame
    #: A column within `cycle` populated from the last `velocity` given in the cstor.
    #: to use in subsequent calculations.
    V: pd.Series
    #: A column derived from :ivar:`V`, also within `cycle`, populated on construction,
    #: and used in subsequent calculations.
    A: pd.Series

    gnames: List[str]

    def __init__(self, *velocities: pd.Series, **kwargs):
        """
        Initialize :ivar:`cycle` with the given velocities and acceleration of the last one.

        :param velocities:
            *named* series, e.g. from :func:`~datamodel.get_class_v_cycle()`,
            all sharing the same time-index  The last one is assumed to be the
            "target" velocity for the rest of the cycle methods.
        """
        c = wio.pstep_factory.get().cycle

        assert velocities and all(
            (isinstance(i, pd.Series) and i.name and not i.empty for i in velocities)
        ), ("Null/empty inputs:", locals())

        vars(self).update(kwargs)

        ## Ensure time index of velocities is the 1st column.
        cycle = pd.DataFrame(
            dict([(c.t, velocities[0].index), *((v.name, v) for v in velocities)])
        )
        V = cycle.iloc[:, -1]
        cycle = cycle.set_index(c.t, drop=False)

        cycle[c.a] = calc_acceleration(V)

        self.cycle = cycle
        self.V = V
        self.A = cycle[c.a]

    def add_wots(self, gwots: pd.DataFrame):
        """
        Adds the `gwots` joined on the ``v_cap`` column of the `cycle`.

        :param gwots:
            a dataframe of wot columns indexed by a grid of rounded velocities,
            as generated by :func:`~engine.interpolate_wot_on_v_grid2()`, and
            augmented by `:func:`~engine.calc_p_avail_in_gwots()`.

        """
        c = wio.pstep_factory.get().cycle
        cycle = self.cycle

        assert all(
            (isinstance(i, pd.DataFrame) for i in (cycle, gwots))
        ) and isinstance(gwots, pd.DataFrame), locals()

        self.ng = len(gwots.columns.levels[0])
        self.gnames = wio.gear_names(range(1, self.ng + 1))
        gwots = gwots.reindex(self.V).swaplevel(axis=1).sort_index(axis=1)
        cycle = pd.concat((cycle.set_index(self.V), gwots), axis=1, sort=False)
        cycle = cycle.set_index(c.t, drop=False)

        self.cycle = cycle

    # TODO: incorporate `validate_nims_t_start()`  in validations pipeline.
    def validate_nims_t_start(self, t_start: int, wltc_parts: Seq[int]):
        c = wio.pstep_factory.get().cycle

        if t_start:
            if t_start > wltc_parts[0]:
                yield ValidationError(
                    "f`t_start`({t_start}) must finish before the 1st cycle-part(t_end={wltc_parts[0]})!"
                )
            if not self.cycle[c.stop].iloc[t_start]:
                yield ValidationError(
                    "f`t_start`({t_start}) must finish on a cycle stop(v={self.V.iloc[t_start]})!"
                )

    def flatten_columns(self, columns):
        sep = self.multi_column_separator

        def join_column_names(name_or_tuple):
            if isinstance(name_or_tuple, tuple):
                return sep.join(n for n in name_or_tuple if n)
            return name_or_tuple

        return [join_column_names(names) for names in columns.to_flat_index()]

    def inflate_columns(self, columns, levels=2):
        sep = self.multi_column_separator

        def split_column_name(name):
            assert isinstance(name, str), ("Inflating Multiindex?", columns)
            names = name.split(sep)
            if len(names) < levels:
                nlevels_missing = levels - len(names)
                names.extend([""] * nlevels_missing)
            return names

        tuples = [split_column_name(names) for names in columns]
        return pd.MultiIndex.from_tuples(tuples, names=["gear", "item"])

    def flat(self) -> pd.DataFrame:
        """return the :ivar:`cycle` with flattened columns"""
        cycle = self.cycle.copy()
        cycle.columns = self.flatten_columns(cycle.columns)
        return cycle


@dataclasses.dataclass
class CycleMarker:
    """Identifies conjecutive truths in series"""

    #: The vehicle is stopped when its velocity is below this number (in kmh),
    #: by Annex 2-4 this is 1.0 kmh.
    running_threshold: float = 1.0

    #: (positive) consider *at least* that many conjecutive samples as
    #: belonging to a `long_{stop/acc/cruise/dec}` generated column,
    #: e.g. for ``phase_repeat_threshold=2`` see the example in :func:`_identify_conjecutive_truths()`.
    #: if 0,unspecified (might break)
    phase_repeat_threshold: int = 2

    #: the acceleration threshold(-0.1389) for identifying n_min_drive_up/down phases,
    #: defined in Annex 2-2.k
    up_threshold: float = -0.1389

    def _identify_conjecutive_truths(
        self, col: pd.Series, right_edge: bool
    ) -> pd.Series:
        """
        Dectect phases with a number of conjecutive trues above some threshold.

        :param col:
            a bolean series
        :param right_edge:
            when true, the `col` includes +1 sample towards the end

        >>> cycle = pd.DataFrame({
        ...          'v': [0,0,3,3,5,8,8,8,6,4,5,6,6],
        ...      'accel': [0,0,0,1,1,1,0,0,0,1,1,1,0],
        ...     'cruise': [0,0,0,0,0,1,1,1,0,0,0,0,0],
        ...      'decel': [0,0,0,0,0,0,0,1,1,1,0,0,0],
        ...         'up': [0,0,1,1,1,1,1,1,0,1,1,1,1],
        ...       'init': [1,0,0,0,0,0,0,0,0,0,0,0,0],
        ... })

        >>> A = (-cycle.v).diff(-1)  # GTR's acceleration definition
        >>> def phase(cond):
        ...     return cycler._identify_conjecutive_truths((cycle.v > 0) & cond, True, 2).astype(int).to_list()
        >>> assert phase(A > 0) == cycle.accel
        True
        >>> assert phase(A == 0) == cycle.cruise
        True
        >>> assert phase(A < 0) == cycle.decel
        True

        Adapted from: https://datascience.stackexchange.com/a/22105/79324
        """
        grouper = (col != col.shift()).cumsum()
        # NOTE: git warns: pandas/core/indexes/base.py:2890: FutureWarning:
        # elementwise comparison failed; returning scalar instead,
        # but in the future will perform elementwise comparison
        col &= col.groupby(grouper).transform("count").ge(self.phase_repeat_threshold)
        if right_edge:
            col |= col.shift()
        return col

    def _identify_last_decel_before_stop(self, cycle):
        last_decel_sample_before_stop = cycle.decel & cycle.stop
        decels = cycle.decel
        decels_grouper = (decels != decels.shift()).cumsum()
        decelstop = (
            decels.groupby(decels_grouper)
            .transform(
                lambda decel_group: decel_group.count()
                if (decel_group & last_decel_sample_before_stop).any()
                else 0
            )
            .gt(0)
        )

        return decelstop

    def add_phase_markers(
        self, cycle: pd.DataFrame, V: pd.Series, A: pd.Series
    ) -> pd.DataFrame:
        """
        Adds accel/cruise/decel/up phase markers into the given cycle,

        based `V` & `A` columns of a cycle generated by :func:`emerge_cycle()`.
        """
        c = wio.pstep_factory.get().cycle

        assert all(i is not None for i in (cycle, V, A)), (
            "Null in inputs:",
            cycle,
            V,
            A,
        )

        ## Mark start from standstill, Annex 2-3.2 about.
        cycle[c.init] = (V == 0) & (A == 0) & (A.shift(-1) != 0)

        ## Annex 2-4
        #
        cycle[c.run] = V >= self.running_threshold
        RUN = cycle[c.run]
        #
        def phase(cond):
            return self._identify_conjecutive_truths(RUN & cond, right_edge=True)

        #
        cycle[c.stop] = ~RUN
        cycle[c.accel] = phase(A > 0)
        cycle[c.cruise] = phase(A == 0)
        cycle[c.decel] = phase(A < 0)

        ## Annex 2-2.k (n_min_drive).
        cycle[c.up] = phase(A >= self.up_threshold)

        cycle[c.decelstop] = self._identify_last_decel_before_stop(cycle)

        cycle.columns = pd.MultiIndex.from_product(
            (cycle.columns, ("",)), names=("item", "gear")
        )

        return cycle

    def add_class_phase_markers(
        self, cycle: pd.DataFrame, wltc_parts: Iterable[int], *, right_edge=True
    ) -> pd.DataFrame:
        """
        Adds low/mid/hight/extra high boolean index into cycle, named as p1, ...

        :param cycle:
            assumes indexed by time
        :param wltc_parts:
            must include edges (see :func:`~datamodel.get_class_parts_limits()`)
        """
        c = wio.pstep_factory.get().cycle

        assert all(i is not None for i in (cycle, wltc_parts)), (
            "Null in inputs:",
            cycle,
            wltc_parts,
        )
        assert isinstance(wltc_parts, Iterable), wltc_parts

        for n, (start, end) in enumerate(itz.sliding_window(2, wltc_parts), 1):
            idx = start <= cycle.index
            if right_edge:
                idx &= cycle.index <= end
            else:
                idx &= cycle.index < end
            cycle[wio.class_part_name(n)] = idx

        return cycle
