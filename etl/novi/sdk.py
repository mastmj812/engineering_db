# this is a library file, check out usage examples in sample.py

import os
import shutil
import sys
import zipfile
from pathlib import Path
from shutil import rmtree, copy2
from typing import List, Iterator, Optional, Tuple, Dict, Set
import requests
import json


class NoviDataException(Exception):
    code: str = None

    def __init__(self, message: str, code: Optional[str] = None):
        super().__init__(message)
        self.code = code


class NoviDataAuthenticationException(NoviDataException):
    pass


class NoviDataDiffMergingException(NoviDataException):
    pass


class NoviDataSdk:
    NONE_DATE = '1800-01-01T00:00:00.000Z'
    EXPORT_DATE_FILE = 'ExportDate.txt'

    def __init__(self, email: str, password: str, data_dir: Path, base: str = 'https://insight.novilabs.com/api/', version: str = 'v3', scope: str='us-horizontals'):
        self._base = base + version
        self._version = version
        self._token = self._authenticate(email, password)
        self._data_dir = data_dir
        self._scope = scope

    def _authenticate(self, email: str, password: str) -> str:
        res = requests.post(self._base + '/sessions', {'email': email, 'password': password})
        if not res.ok:
            raise NoviDataAuthenticationException('Unable to authenticate: ' + res.text)
        return res.json()['authentication_token']

    def request(self, url, params: dict = None) -> Iterator[dict]:
        page = 1
        while True:
            data = self.raw_request(url, {'page': page, **(params or {})})

            if len(data) == 0:
                # no more data, stop iterating over pages
                break
            page += 1

            yield from data

    def request_one(self, url, params: dict = None) -> dict:
        data = self.raw_request(url, params or {})
        if self._version == 'v1' and type(data) == dict:
            return data

        if len(data) != 1:
            raise NoviDataException(f'Query expected a single result, {len(data)} found')
        return data[0]

    def raw_request(self, url, params: dict = None) -> List[dict]:
        res = requests.get(
            self._base + url,
            params={
                'authentication_token': self._token,
                'scope': self._scope,
                **(params or {}),
            }
        )

        if not (200 <= res.status_code < 400):
            try:
                content = res.json()
                raise NoviDataException('Status code: %s; error: %s' % (res.status_code, content['message']), content.get('error_code'))
            except json.JSONDecodeError:
                raise NoviDataException('Status code: %s; content: %s' % (res.status_code, res.content))

        return res.json()

    def update_bulk_data(self, scope: Optional[str] = None, basin: Optional[str] = None, subbasin: Optional[str] = None, no_diffs: bool = False) -> Path:
        bulk_dir = self._data_dir / (scope or self._scope) / (basin or 'All basins') / (subbasin or 'All subbasins')
        target_dir = bulk_dir / 'Bulk'
        last_downloaded = self.read_file(bulk_dir / self.EXPORT_DATE_FILE) or self.NONE_DATE

        params = {'scope': scope or self._scope}
        if basin:
            params['q[Basin_eq]'] = basin
        if subbasin:
            params['q[Subbasin_eq]'] = subbasin
        latest_export = self.request_one('/bulk', params)

        print('Latest export available for download:', latest_export['ExportDate'])
        print('Latest export downloaded:', last_downloaded)

        if latest_export['ExportDate'] <= last_downloaded:
            print('The currently downloaded export is the most current one, skipping download')

            return target_dir

        if self._version in ['v1', 'v2'] or last_downloaded == self.NONE_DATE or no_diffs:
            return self._fetch_bulk_data_file(target_dir, latest_export['URL'], latest_export['ExportDate'])

        try:
            diffs = list(self.raw_request('/bulk-diffs', {
                'scope': scope or self._scope,
                'q[Basin_eq]': basin or '',
                'q[Subbasin_eq]': subbasin or '',
                'since': last_downloaded,
            }))
        except NoviDataException as e:
            if e.code == 'force_full_download':
                print('Cannot apply diffs in this period, fetching the full export instead')
                return self._fetch_bulk_data_file(target_dir, latest_export['URL'], latest_export['ExportDate'])

            raise e

        if len(diffs) > 30:
            print(f'There are {len(diffs)} diffs to apply, falling back to just downloading a single whole file')
            return self._fetch_bulk_data_file(target_dir, latest_export['URL'], latest_export['ExportDate'])

        tmp_dir_base = self._data_dir / '_tmp' / (scope or self._scope) / (basin or 'All basins') / (subbasin or 'All subbasins')
        # LOCAL PATCH: the diff loop below reassigns `latest_export` to each diff
        # (which carries DiffURL, not the full-export URL), so capture the full
        # export now for use by the full-download fallbacks below.
        full_export = latest_export
        try:
            diff_tmp_dirs = []
            for diff in diffs:
                diff_tmp_dirs.append(self._fetch_bulk_data_file(
                    tmp_dir_base / diff['ExportDate'].replace(':', '_') / 'Bulk',
                    diff['DiffURL'],
                    diff['ExportDate']
                ))
                latest_export = diff

            shp_dir = self._fetch_bulk_data_file(
                tmp_dir_base / '_shp' / 'Shapefiles',
                latest_export['ShapefileURL'],
                None
            )

            # LOCAL PATCH: merge_bulk_diffs reads schema.json from the *current*
            # (pre-rename) bulk dir. If it is missing, the merge raises only after
            # target_dir has been renamed away, and the `finally` below then deletes
            # the live data. Detect it here -- before touching anything -- and fall
            # back to a full download instead.
            if not (target_dir / 'schema.json').exists():
                print('Current bulk data has no schema.json; cannot diff-merge, fetching the full export instead')
                return self._fetch_bulk_data_file(target_dir, full_export['URL'], full_export['ExportDate'])

            current_tmp_dir = target_dir.rename(tmp_dir_base / 'current')

            self.merge_bulk_diffs(
                current_tmp_dir,
                diff_tmp_dirs,
                target_dir,
            )

            shp_target = target_dir / 'Shapefiles'
            if shp_target.exists():
                rmtree(shp_target)
            shp_dir.rename(shp_target)

            self.write_file(target_dir.parent / self.EXPORT_DATE_FILE, latest_export['ExportDate'])

            return target_dir
        except Exception as e:
            # LOCAL PATCH: broadened from NoviDataDiffMergingException. By this point
            # target_dir may already be renamed into tmp_dir_base, and the finally
            # below will delete it -- so ANY merge failure (missing schema.json,
            # malformed diff, I/O error) must recover via a full download rather than
            # propagate and lose the local cache. Uses full_export, not latest_export
            # (which the diff loop reassigned to a diff lacking the full-export URL).
            print(f'Error while merging diffs, falling back to a full download. Error message: {str(e)}')
            return self._fetch_bulk_data_file(target_dir, full_export['URL'], full_export['ExportDate'])
        finally:
            # ignore_errors so a cleanup failure can't mask the real exception above
            shutil.rmtree(tmp_dir_base, ignore_errors=True)

    def _fetch_bulk_data_file(self, target_dir: Path, url: str, export_date: Optional[str]):
        print(f'Downloading {url} to {target_dir}')
        self._ensure_empty_dir(target_dir.parent)
        zip_file = self._download_file(url, target_dir.parent / 'Bulk.zip')
        self._unzip(zip_file, target_dir)
        if export_date:
            self.write_file(target_dir.parent / self.EXPORT_DATE_FILE, export_date)

        return target_dir

    def _download_file(self, url, target):
        res = requests.get(url, stream=True)
        if not (200 <= res.status_code < 400):
            raise NoviDataException('Status code: %s' % res.status_code)

        total_size = int(res.headers.get('content-length', res.headers.get('X-DB-Content-length', 1)))
        block_size = 1024
        print('Downloading %s to %s, size: %s' % (url, target, self._format_bytes(total_size)))
        downloaded_size = 0
        with open(target, 'wb') as f:
            for chunk in res.iter_content(chunk_size=block_size):
                if chunk:
                    f.write(chunk)
                    downloaded_size += block_size
                    sys.stdout.write(f'\rProgress: {self._format_bytes(downloaded_size)} / {self._format_bytes(total_size)} ({round(100 * downloaded_size / total_size, 2)}%)        ')
                    sys.stdout.flush()
        print()

        return target

    @staticmethod
    def _format_bytes(num):
        for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi', 'Yi']:
            if abs(num) < 1024.0:
                return "%3.1f%sB" % (num, unit)
            num /= 1024.0

    @staticmethod
    def _unzip(source, target):
        print('Unzipping %s to %s' % (source, target))
        zip = zipfile.ZipFile(str(source), 'r')
        zip.extractall(target)
        zip.close()
        print()

        return target

    @staticmethod
    def _ensure_empty_dir(dir):
        if os.path.exists(dir):
           rmtree(dir)
        os.makedirs(dir)

        return dir

    @staticmethod
    def read_file(filename: Path, encoding='utf-8') -> Optional[str]:
        if not os.path.exists(filename):
            return None

        with open(filename, 'r', encoding=encoding) as f:
            return f.read()

    @staticmethod
    def write_file(filename: Path, content: str, encoding='utf-8'):
        with open(filename, 'w+', encoding=encoding) as f:
            f.write(content)

    def merge_bulk_diffs(self, current_dir: Path, diff_dirs: List[Path], target_dir: Path) -> Path:
        if target_dir == current_dir:
            raise NoviDataDiffMergingException('Cannot apply diffs in-place')
        print('Performing a diff merge:', current_dir, ' + ', diff_dirs, ' -> ', target_dir)
        self._ensure_empty_dir(target_dir)

        files_operations = self.__plan_files_operations(current_dir, diff_dirs)

        schema = json.load(open(current_dir / 'schema.json'))

        for relative_file, operations in files_operations.items():
            target_file = target_dir / relative_file
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.unlink(missing_ok=True)

            last_replace_index = max((index for index, (action, _) in enumerate(operations) if action == 'replace'), default=None)
            if last_replace_index:
                operations = operations[last_replace_index:]

            file_to_overwrite, rows_to_overwrite, has_diffs, pk_length, header = self.__apply_operations(operations, relative_file, schema)

            if file_to_overwrite and not has_diffs:
                copy2(file_to_overwrite, target_file)

            if has_diffs:
                self.__apply_diff(
                    file_to_overwrite or current_dir / relative_file,
                    target_dir / relative_file,
                    header,
                    pk_length,
                    rows_to_overwrite
                )

        return target_dir

    def __plan_files_operations(self, current_dir: Path, diff_dirs: List[Path]) -> Dict[Path, List[Tuple[str, Path]]]:
        files_operations = {}

        for diff_dir in diff_dirs:
            for item in diff_dir.rglob('*'):
                if item.is_dir():
                    continue
                relative_name = item.relative_to(diff_dir)
                if relative_name.name.endswith('--diff.tsv'):
                    relative_name = relative_name.with_name(relative_name.name.replace('--diff.tsv', '.tsv'))

                if relative_name not in files_operations:
                    files_operations[relative_name] = []

                if not (current_dir / relative_name).exists() or not self.__is_bulk_diff_file(item):
                    files_operations[relative_name].append(('replace', item))
                else:
                    files_operations[relative_name].append(('apply_diff', item))

        return files_operations

    def __is_bulk_diff_file(self, file: Path) -> bool:
        if file.suffix != '.tsv':
            return False

        if file.name.endswith('--diff.tsv'):
            return True

        # legacy
        with open(file, 'r') as f:
            first_line = f.readline().rstrip()
            return first_line.endswith('\t__deleted')

    def __split_diff_line(self, line: str, pk_length: int, is_legacy_diff: bool = False) -> Tuple[str, str, Optional[bool]]:
        tab_count = 0
        i = 0
        while True:
            char = line[i]
            if char == '\t':
                tab_count += 1
                if tab_count == pk_length:
                    pk_tab_position = i
                    break
            i += 1

        return (
            line[:pk_tab_position],
            line[pk_tab_position+1 : -3 if is_legacy_diff else None],
            line[-1:] == 't' if is_legacy_diff else None,
        )

    def __apply_operations(self, operations: List[Tuple[str, Path]], relative_file: Path, schema)\
            -> Tuple[Optional[Path], Dict[str, str], bool, Optional[int], Optional[str]]:
        file_to_overwrite = None
        rows_to_overwrite: Dict[str, str] = dict()
        has_diffs = False
        pk_length = None
        header = None

        for operation, operation_item in operations:
            if operation == 'replace':
                file_to_overwrite = operation_item
            elif operation == 'apply_diff':
                has_diffs = True
                if pk_length is None:
                    pk_length = len(schema[relative_file.stem]['primary_key'])
                    if not pk_length:
                        raise NoviDataDiffMergingException(
                            f'Cannot apply diff on file {relative_file}: empty primary key')

                with open(operation_item, 'r') as f:
                    is_legacy = False
                    for i, line in enumerate(f.readlines()):
                        line = line.replace('\n', '').replace('\r', '')
                        if i == 0:
                            header = line
                            if '\t__deleted' in header:
                                header = header.replace('\t__deleted', '')
                                is_legacy = True
                            continue
                        pk, content, _ = self.__split_diff_line(line, pk_length, is_legacy)
                        rows_to_overwrite[pk] = content
        return file_to_overwrite, rows_to_overwrite, has_diffs, pk_length, header

    def __apply_diff(self, current_file: Path, target_file: Path, header: str, pk_length: int, to_overwrite: Dict[str, str]):
        with open(target_file, 'w+') as fw:
            with open(current_file, 'r') as fr:
                for i, line in enumerate(fr.readlines()):
                    if i == 0:
                        if line.rstrip() != header:
                            raise NoviDataDiffMergingException('File header has changed, diff cannot be applied')
                        fw.write(line)
                        continue
                    pk, content, _ = self.__split_diff_line(line.rstrip(), pk_length)
                    if pk not in to_overwrite:
                        if line.endswith('\t\n'):  # skip lines with non-empty last column (DeletedAt)
                            fw.write(line)
            for pk, content in to_overwrite.items():
                if content.endswith('\t'):  # skip lines with non-empty last column (DeletedAt)
                    fw.write(pk + '\t' + content + '\n')
