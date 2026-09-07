"""SQL aggregates over verified prospective snapshots, separated by model."""
from html import escape
from math import log


def tracker_body(connection, version=None):
    if not connection:
        return '<h2>Prediction Tracker</h2><p>No database configured yet.</p>'
    models = [r[0] for r in connection.execute("SELECT DISTINCT model_version FROM predictions WHERE evidence_status='verified' ORDER BY model_version")]
    if version is None and models:
        version = connection.execute('SELECT model_version FROM prediction_snapshots ORDER BY id DESC LIMIT 1').fetchone()[0]
    if version is not None and version not in models:
        return '<h2>Prediction Tracker</h2><p>No verified predictions for this model.</p>'
    connection.create_function('binary_loss', 2, lambda p, o: -o * log(max(p, 1e-12)) - (1-o) * log(max(1-p, 1e-12)))
    params = (version,)
    where = "evidence_status='verified' AND model_version=?"
    settled = where + " AND grading_status='settled' AND actual_outcome IN (0,1)"
    legacy = connection.execute("SELECT COUNT(*) FROM predictions WHERE evidence_status!='verified'").fetchone()[0]
    missed = connection.execute("""SELECT COUNT(*) FROM fixtures f WHERE julianday(f.kickoff)<julianday('now')
        AND NOT EXISTS(SELECT 1 FROM predictions p WHERE p.fixture_id=f.id AND p.evidence_status='verified')""").fetchone()[0]
    counts = connection.execute(f'''SELECT COUNT(*) AS forecasts,COUNT(DISTINCT fixture_id) AS fixtures,
        SUM(grading_status='settled') AS settled,SUM(grading_status='pending') AS pending,
        SUM(grading_status='missing_result') AS missing,
        SUM(grading_status NOT IN ('pending','settled','missing_result')) AS review FROM predictions WHERE {where}''', params).fetchone()
    summary = connection.execute(f'''SELECT COUNT(*) AS n,AVG((predicted_probability-actual_outcome)*(predicted_probability-actual_outcome)) AS brier,
        AVG(binary_loss(predicted_probability,actual_outcome)) AS loss FROM predictions WHERE {settled}''', params).fetchone()
    pct = lambda x: '-' if x is None else f'{x:.1%}'
    number = lambda x: '-' if x is None else f'{x:.4f}'
    body = f'''<h2>Prediction Tracker</h2><p>Model: {escape(version or 'none')}. Frozen before kickoff; prospective records only.</p>
        <p>{counts['fixtures']} fixtures / {counts['forecasts']} probability forecasts.
        Settled: {counts['settled'] or 0}; pending: {counts['pending'] or 0}; missing results: {counts['missing'] or 0};
        requires review: {counts['review'] or 0}. Legacy unverified forecasts excluded: {legacy}.</p>
        <p>Known past fixtures without a verified snapshot: {missed}. Fixtures never discovered cannot be counted.</p>
        <p>All-outcome Brier: {number(summary['brier'])}; log loss: {number(summary['loss'])}; sample: {summary['n']}.</p>
        <p>Pick hit rate measures the displayed selection: highest-probability winner and BTTS + winner,
        plus Over 2.5 and BTTS Yes. Ties follow the frozen model output order. It is not the average of all possible winners.
        These overlapping markets are correlated; forecast counts are not independent match counts.
        Missing and excluded outcomes may bias the settled sample. Small samples are inconclusive.</p>'''
    refresh = connection.execute('SELECT * FROM refresh_runs ORDER BY id DESC LIMIT 1').fetchone()
    if refresh:
        body += f"<p>Last refresh: {escape(refresh['started_at'])} — {escape(refresh['status'])}.</p>"
    else:
        body += '<p>No recorded scheduled refresh yet.</p>'
    if models:
        from urllib.parse import urlencode
        body += '<p>Models: ' + ' | '.join(f'<a href="/performance?{urlencode({"model": m})}">{escape(m)}</a>' for m in models) + '</p>'
    for title, expression in [('Overall displayed picks', "'All picks'"), ('By League', 'competition'),
                              ('By Market', 'market_group'), ('By Probability Range', 'probability_bucket'),
                              ('Home / away / draw picks', "CASE WHEN market LIKE 'home_%' THEN 'Home' WHEN market LIKE 'away_%' THEN 'Away' WHEN market='draw' THEN 'Draw' ELSE 'Totals / BTTS' END")]:
        rows = connection.execute(f'''SELECT {expression} AS label,COUNT(*) AS n,COUNT(DISTINCT fixture_id) AS fixtures,
            AVG(actual_outcome) AS hit,AVG(predicted_probability) AS probability FROM predictions
            WHERE {settled} AND is_pick=1 GROUP BY 1 ORDER BY 1''', params).fetchall()
        body += f'<h3>{title}</h3><table><tr><th>Group</th><th>Picks</th><th>Fixtures</th><th>Hit rate</th><th>Mean probability</th></tr>'
        body += ''.join(f"<tr><td>{escape(r['label'] or 'Unknown')}</td><td>{r['n']}</td><td>{r['fixtures']}</td><td>{pct(r['hit'])}</td><td>{pct(r['probability'])}</td></tr>" for r in rows) + '</table>'
    body += '<h3>Calibration — all probabilities, by individual market</h3><table><tr><th>Market</th><th>Range</th><th>Sample</th><th>Predicted</th><th>Occurred</th></tr>'
    rows = connection.execute(f'''SELECT market,probability_bucket,COUNT(*) AS n,AVG(predicted_probability) AS p,
        AVG(actual_outcome) AS actual FROM predictions WHERE {settled} GROUP BY market,probability_bucket ORDER BY market,probability_bucket''', params).fetchall()
    body += ''.join(f"<tr><td>{escape(r['market'])}</td><td>{escape(r['probability_bucket'])}</td><td>{r['n']}</td><td>{pct(r['p'])}</td><td>{pct(r['actual'])}</td></tr>" for r in rows) + '</table>'
    return body
