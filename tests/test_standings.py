import pytest
from matchsignal.standings import parse_sky_table
from matchsignal.leagues import LEAGUES

def content(rows=10):
    return '<title>Scottish League 2 Table | Sky Sports</title><table>'+''.join(
        f'<tr><td data-live-key="pos">{i}</td><td data-live-key="team"><span>Club {i}</span></td><td data-live-key="pld">7</td></tr>'
        for i in range(1,rows+1))+'</table>'

def test_publisher_positions_preserved():
    rows=parse_sky_table(content(),LEAGUES[-1])
    assert len(rows)==10 and rows[-1]['position']==10

def test_redirect_and_partial_tables_rejected():
    with pytest.raises(ValueError):parse_sky_table(content(),LEAGUES[0])
    with pytest.raises(ValueError):parse_sky_table(content(4),LEAGUES[-1])
