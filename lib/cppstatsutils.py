# -*- coding: utf-8 -*-
# cppstats is a suite of analyses for measuring C preprocessor-based
# variability in software product lines.
# Copyright (C) 2010-2015 University of Passau, Germany
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU Lesser General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this program.  If not, see
# <http://www.gnu.org/licenses/>.
#
# Contributors:
#     Wolfram Fenske <wfenske@ovgu.de>

import os

def logParseProgress(fcount, ftotal, folder, fn):
    path = os.path.relpath(os.path.join(folder, fn), os.getcwd())
    sFtotal = str(ftotal)
    print 'INFO parsing file %*d/%s: %s' % (len(sFtotal), fcount, sFtotal, path)
