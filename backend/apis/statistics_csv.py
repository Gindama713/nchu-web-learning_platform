"""Serialize only the saved 010B result, in page order and at page precision."""

import csv
import io
import json

from flask import make_response


def cell(value):
    if value is None:
        return ''
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    if isinstance(value, str) and (value.startswith(('\t', '\r', '\n')) or
                                   value.lstrip().startswith(('=', '+', '-', '@'))):
        return "'" + value
    return value


def response(data):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)

    def row(values):
        writer.writerow([cell(value) for value in values])

    for key in ('analysis_run_id', 'dimension', 'source_until', 'generated_at', 'algorithm_version',
                'sample_size', 'population_basis', 'unit', 'warnings'):
        row([key, data[key]])
    row(['filters', data.get('filters')])
    metrics = data['metrics']
    keys = [key for key in metrics if key not in ('items', 'score_bins')]
    # Explicit keys rather than JSON object order (Flask may sort response keys).
    keys.sort()
    row(['section', 'period_start', 'period_end', *keys])
    row(['overall', '', '', *(metrics[key] for key in keys)])
    for item in data['series']:
        row(['series', item['period_start'], item['period_end'], *(item['metrics'][key] for key in keys)])
    if data['dimension'] == 'knowledge':
        columns = ('knowledge_id', 'title', 'answered_count', 'correct_count', 'wrong_count', 'mastery')
        row(['knowledge_items', *columns])
        for item in metrics['items']:
            row(['item', *(item[key] for key in columns)])
        row(['knowledge_series_items', 'period_start', 'period_end', *columns])
        for period in data['series']:
            for item in period['metrics']['items']:
                row(['series_item', period['period_start'], period['period_end'], *(item[key] for key in columns)])
    else:
        row(['score_bins', 'period_start', 'period_end', 'label', 'count'])
        for item in metrics['score_bins']:
            row(['overall_bin', '', '', item['label'], item['count']])
        for period in data['series']:
            for item in period['metrics']['score_bins']:
                row(['series_bin', period['period_start'], period['period_end'], item['label'], item['count']])
    download = make_response('\ufeff' + stream.getvalue())
    download.headers['Content-Type'] = 'text/csv; charset=utf-8'
    download.headers['Content-Disposition'] = f'attachment; filename="{data["dimension"]}-{data["analysis_run_id"]}.csv"'
    return download
