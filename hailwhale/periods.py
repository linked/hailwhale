from datetime import datetime, timedelta, date
import time
import times
import pytz; pytznow = lambda: datetime.now(pytz.utc)
import re
PARSED = {}
PERIODS = [
#{'name': 'Last 3 years, by month', 'length': '3y', 'interval': '1d', 'nickname': 'monthly'},
{'name': 'Last year, by day',
    'length': '1y',
    'interval': '1d',
    'nickname': 'year'},
{'name': 'Last 30 days, by day', 'length': '1mo', 'interval': '1d',
    'nickname': 'thirty'},
{'name': 'Last week, by day', 'length': '1w', 'interval': '1d',
    'nickname': 'seven'},
{'name': 'Last day, by hour', 'length': '1d', 'interval': '1h',
    'nickname': 'day'},
{'name': 'Last hour, by 1 minutes', 'length': '1h', 'interval': '1m',
    'nickname': 'hour'},
{'name': 'Month to date', 'length': '1mo', 'interval': '1d', 'nickname': 'mtd'},
{'name': 'Year to date', 'length': '1y', 'interval': '1d',
    'nickname': 'ytd'}
]


UnitMultipliers = {
  'seconds' : 1,
  'minutes' : 60,
  'hours' : 3600,
  'days' : 86400,
  'weeks' : 86400 * 7,
  'months' : 86400 * 31,
  'years' : 86400 * 365
}


def getUnitString(s):
  if 'seconds'.startswith(s): return 'seconds'
  if 'minutes'.startswith(s): return 'minutes'
  if 'hours'.startswith(s): return 'hours'
  if 'days'.startswith(s): return 'days'
  if 'weeks'.startswith(s): return 'weeks'
  if 'months'.startswith(s): return 'months'
  if 'years'.startswith(s): return 'years'
  raise ValueError("Invalid unit '%s'" % s)

def parseUnit(unit):
    if str(unit).isdigit():
        return int(unit) * UnitMultipliers[getUnitString('s')]
    unit_re = re.compile(r'^(\d+)([a-z]+)$')
    match = unit_re.match(str(unit))
    if match:
      unit = int(match.group(1)) * UnitMultipliers[getUnitString(match.group(2))]
    else:
      raise ValueError("Invalid unit specification '%s'" % unit)
    return unit

def parseRetentionDef(retentionDef):
  (precision, points) = retentionDef.strip().split(':')
  precision = parseUnit(precision)

  if points.isdigit():
    points = int(points)
  else:
    points = parseUnit(points) / precision

  return (precision, points)

class Period(object):
    def __init__(self, interval, length, name=False, nickname=False):
        self.interval = str(interval)
        self.length = str(length)
        self.name = name
        self.nickname = nickname
        self.units = self.getUnits()
        self._ats_cache = {}

    def getUnits(self):
        return parseUnit(self.interval), parseUnit(self.length)

    @classmethod
    def parse(cls, formula, tzoffset=0):
        formula = str(formula)
        if '|' in formula:
            formula, tzoffset = formula.split('|')
        p = cls.lookup('thirty')
        start = end = None
        now = convert(pytznow(), tzoffset)
        if formula == 'ytd':
            p = cls.lookup('year')
            start = now.replace(month=1, day=1,hour=0,minute=0,second=0, microsecond=0)
        elif formula == 'mtd':
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        elif formula == 'wtd':
            end = now.replace(hour=0, minute=0, second=0, microsecond=0)
            start = end - timedelta(now.weekday() + 2)
        elif formula in ['24h', 'hours']:
            p = cls.lookup('day')
            end = now.replace(minute=0, second=0, microsecond=0)
            start = now - timedelta(hours=24)
        elif formula in ['today']:
            p = cls.lookup('day')
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif formula in ['hour']:
            p = cls.lookup('hour')
            end = now.replace(second=0, microsecond=0)
            start = end - timedelta(hours=1)
        elif formula == 'yesterday':
            end = now.replace(hour=0, minute=0, second=0, microsecond=0)
            start = end - timedelta(1)
            end = end - timedelta(seconds=1)
        elif formula == 'seven':
            start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(7)
        elif '-' in str(formula):
            start_s, end_s = formula.split('-')
            p = cls.lookup('year')
            end = datetime.strptime(end_s, '%m/%d/%Y').replace(hour=0, minute=0,
                    second=0, microsecond=0)+timedelta(1)-timedelta(seconds=1)
            start = datetime.strptime(start_s, '%m/%d/%Y').replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            p = cls.lookup(formula)
        return p, start, end, tzoffset

    @classmethod
    def get_days(cls, formula, at=None, tzoffset=0):
        ats = False
        p, start, end, tzoffset = cls.parse(formula, tzoffset)
        if tzoffset in p._ats_cache:
            ats, ts = p._ats_cache[tzoffset]
            if ats and (time.time() - ts) <= 60:
                return p, ats, tzoffset
        ats = list(p.datetimes_strs(start=start, end=end, tzoffset=tzoffset))
        if not ats and not at:
            ats = list(p.datetimes_strs(tzoffset=tzoffset))
        elif not ats:
            ats = [p.flatten_str(convert(at, tzoffset))]
        p._ats_cache[tzoffset] = ats, time.time()
        return p, ats, tzoffset

    def start(self, tzoffset):
        interval, length = self.units
        dt= convert(pytznow(), tzoffset) - timedelta(seconds=length)
        if interval < 60:
            interval_seconds = interval
        else: interval_seconds = 60
        if interval < 3600:
            interval_minutes = (interval - interval_seconds)/60
        else: interval_minutes = 60
        if interval < 3600*24:
            interval_hours = (interval - interval_seconds -
                    (60*interval_minutes))/3600
        else:
            interval_hours = 24
        if interval_hours == 0: interval_hours = 1
        if interval_minutes == 0: interval_minutes = 1
        new_start = dt.replace(
            microsecond = 0,
            second = (dt.second - dt.second%interval_seconds),
            minute = (dt.minute - dt.minute%interval_minutes),
            hour = (dt.hour - dt.hour%interval_hours),)
        if interval >= (3600*24*30):
            new_start = new_start.replace(day=1)
        new_start = new_start.replace(tzinfo=None)
        return new_start
    @staticmethod
    def format_dt_str(t):
        return t.strftime('%a %b %d %H:%M:%S %Y')
    @staticmethod
    def parse_dt_str(t):
        #if t in PARSED: return PARSED[t]
        try:
            from dateutil import parser
            val = parser.parse(t)
        except ValueError:
            val = None
        PARSED[t] = val
        return val

    def datetimes(self, start=False, end=False, tzoffset=0):
        from dateutil import rrule
        from util import datetimeIterator
        use_start = start or self.start(tzoffset)
        use_end = end or convert(pytznow(), tzoffset)
        use_start = use_start.replace(tzinfo=None)
        use_end = use_end.replace(tzinfo=None)
        interval, length = self.units
        if interval >= 3600*24*30:
            rule = rrule.MONTHLY
            step = interval / (3600*24*30)
        elif interval >= 3600*24*7:
            rule = rrule.WEEKLY
            step = interval / (3600*24*7)
        elif interval >= 3600*24:
            rule = rrule.DAILY
            step = interval / (3600*24)
        elif interval >= 3600:
            rule = rrule.HOURLY
            step = interval / 3600
        elif interval >= 60:
            rule = rrule.MINUTELY
            step = interval / 60
        else:
            rule = rrule.SECONDLY
            step = interval
        dts = [
            dt for dt in
            rrule.rrule(rule, dtstart=use_start, until=use_end, interval=step)
        ]
        return dts

    def datetimes_strs(self, start=False, end=False, tzoffset=0):
        return (Period.format_dt_str(dt) for dt in
                self.datetimes(start=start, end=end, tzoffset=tzoffset))

    def flatten(self, dtf=None):
        """
        Take a datetime, flatten it to this period,
        return M/D/Y H:00:00 or H:MM:00 and etc
        Returns None if out of timerange
        """
        # Default to now
        if not dtf:
            dtf = pytznow()
        # Or parse the string
        if type(dtf) in (str, unicode):
            dtf = self.parse_dt_str(dtf)

        # Convert UTCOffsetSeconds to "-0700"
        _conv = 3600 * 1/100
        offset = dtf.tzinfo and dtf.utcoffset().total_seconds()/_conv or 0

        # TODO We should be memoizing this method call
        dts = list(self.datetimes(end=dtf, tzoffset=offset))

        return len(dts) and dts[-1] or False

    def flatten_str(self, dtf):
        f = self.flatten(dtf)
        if not f:
            return False
        return self.format_dt_str(f)

    def __unicode__(self):
        return '%s:%s' % (self.interval, self.length)

    def __str__(self):
        return '%s:%s' % (self.interval, self.length)

    @staticmethod
    def all_sizes():
        return PERIOD_OBJS

    @staticmethod
    def all_sizes_dict():
        return dict(map(lambda p: ('%s:%s' % (p.interval, p.length), p),
            Period.all_sizes()))

    @staticmethod
    def interval_sizes_dict():
        return MAX_INTERVALS

    @staticmethod
    def lookup(name=None):
        if isinstance(name, Period):
            return name
        if name and name in PERIOD_NICKS:
            return PERIOD_NICKS[str(name)]
        if not name or name == 'None':
            name = Period.default_size()
        if str(name) in Period.all_sizes_dict():
            return Period.all_sizes_dict()[str(name)]
        try:
            return PERIOD_INTERVALS[parseUnit(name)]
        except:
            raise KeyError(name)

    @staticmethod
    def get(formula=None):
        return Period.parse(formula)[0]



    @staticmethod
    def default_size():
        return str(Period.all_sizes()[1])
    @staticmethod
    def convert(tz, tzo):
        return convert(tz, tzo)

    def friendly_name(self):
        return self.name if self.name else '%s:%s' % (
                self.interval, self.length)

PERIOD_OBJS = []
PERIOD_NICKS = {}
PERIOD_INTERVALS = {}
MAX_INTERVALS = {}
for p in PERIODS:
    period = Period(p['interval'], p['length'], p['name'], p.get('nickname', None))
    PERIOD_OBJS.append(period)
    PERIOD_INTERVALS[parseUnit(p['interval'])] = period
    if 'nickname' in p:
        PERIOD_NICKS[p['nickname']] = period
        PERIOD_NICKS[p['interval']] = period
DEFAULT_PERIODS = Period.all_sizes()
for p in PERIOD_OBJS:
    i = p.interval
    if i not in MAX_INTERVALS or MAX_INTERVALS[i].units[1] < p.units[1]:
        MAX_INTERVALS[p.interval] = p
def convert(tzs, tzoffset=None):
    if tzoffset == 'system':
        tzoffset = (time.timezone / -(60*60) * 100)
    if not tzoffset:
        return tzs
    elif isinstance(tzs, datetime):
        return tzs + timedelta(hours=float(tzoffset)/100)
    elif isinstance(tzs, basestring):
        return times.format(tzs, int(tzoffset))
    elif isinstance(tzs, int):
        return tzs + int(3600*float(tzoffset)/100)
    elif isinstance(tzs, list):
        return map(lambda tz: convert(tz, float(tzoffset)), tzs)
