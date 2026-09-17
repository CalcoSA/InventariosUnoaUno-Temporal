from app.constants import SUMMARY_HEADERS


class GeneralSummaryRepository:
    def __init__(self, sheets, book_id):
        self.sheets, self.book_id = sheets, book_id
        self.title = 'Resumen General'

    def ensure_sheet(self):
        if self.sheets.find_sheet(self.book_id, self.title):
            return
        first = self.sheets.metadata(self.book_id).get('sheets', [])
        if first and not self.sheets.read(self.book_id, first[0]['properties']['title'], display=True):
            self.sheets.batch(self.book_id, [{'updateSheetProperties': {'properties': {
                'sheetId': first[0]['properties']['sheetId'], 'title': self.title}, 'fields': 'title'}}])
        else:
            self.sheets.ensure_sheet(self.book_id, self.title)

    def prepare(self):
        self.ensure_sheet()
        if not self.sheets.read(self.book_id, self.title):
            self.sheets.write(self.book_id, self.title, 1, [SUMMARY_HEADERS])

    def rows(self):
        return self.sheets.read(self.book_id, self.title)[1:]

    def load_for_save(self):
        metadata = self.sheets.metadata(self.book_id)
        sheets = metadata.get('sheets', [])
        if any(s['properties']['title'] == self.title for s in sheets):
            return metadata, self.sheets.read(self.book_id, self.title), None
        if sheets:
            first = sheets[0]['properties']['title']
            if not self.sheets.read(self.book_id, first, display=True):
                return metadata, [], first
        return metadata, [], None

    def save_changes(self, metadata, previous, updates, additions, rename_from=None):
        groups = []
        if not previous:
            groups.append((1, [SUMMARY_HEADERS], 1))
        for number, values in sorted(updates):
            if groups and number == groups[-1][0] + len(groups[-1][1]):
                groups[-1][1].append(values)
            else:
                groups.append((number, [values], 1))
        if additions:
            groups.append((max(1, len(previous)) + 1, additions, 1))
        self.sheets.write_documents(self.book_id, metadata, [
            {'title': self.title, 'updates': groups, 'columns': 10, 'freeze': True,
             'format_header': not previous, 'rename_from': rename_from}])

    def update(self, row, values):
        self.sheets.write(self.book_id, self.title, row, [values])

    def update_many(self, updates):
        # Mismos rangos finales; agrupar evita una llamada REST por cada producto.
        groups = []
        for number, values in sorted(updates):
            if groups and number == groups[-1][0] + len(groups[-1][1]):
                groups[-1][1].append(values)
            else:
                groups.append((number, [values], 1))
        self.sheets.write_ranges(self.book_id, self.title, groups)

    def append(self, rows):
        if rows:
            self.sheets.append(self.book_id, self.title, rows)

    def format(self):
        self.sheets.format_header(self.book_id, self.title, 10, freeze=True, resize=True)

    def replace(self, rows):
        self.ensure_sheet()
        self.sheets.clear(self.book_id, self.title)
        self.sheets.write(self.book_id, self.title, 1, [SUMMARY_HEADERS] + rows)
        self.format()
