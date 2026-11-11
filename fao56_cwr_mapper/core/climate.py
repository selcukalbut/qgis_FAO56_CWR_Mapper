"""Daily climate record shared by all climate sources (NASA POWER, station CSV)."""


class DailyClimate:
    """One day of weather; missing values are None.

    tmax, tmin, tdew [degC]; rh, rhmax, rhmin [%] (rh = daily mean); u2 [m s-1]
    at 2 m; rs [MJ m-2 day-1]; sunshine = actual sunshine duration n [hour];
    precip [mm].
    """

    __slots__ = ("day", "tmax", "tmin", "tdew", "rh", "u2", "rs", "precip",
                 "rhmax", "rhmin", "sunshine")

    def __init__(self, day, tmax, tmin, tdew, rh, u2, rs, precip,
                 rhmax=None, rhmin=None, sunshine=None):
        self.day = day
        self.tmax = tmax
        self.tmin = tmin
        self.tdew = tdew
        self.rh = rh
        self.u2 = u2
        self.rs = rs
        self.precip = precip
        self.rhmax = rhmax
        self.rhmin = rhmin
        self.sunshine = sunshine

    def __repr__(self):
        return "DailyClimate({})".format(", ".join(
            "{}={!r}".format(k, getattr(self, k)) for k in self.__slots__
            if getattr(self, k) is not None or k in ("day", "tmax", "tmin")))
