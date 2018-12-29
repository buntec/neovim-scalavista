import requests
import pynvim


DEFAULT_PORT = 9317


def get_offset_from_cursor(buf, cursor):
    line = cursor[0]
    col = cursor[1]
    offset = 0
    for i in range(line - 1):
        offset += len(buf[i]) + 1
    offset += col
    return offset


@pynvim.plugin
class Scalavista(object):

    def __init__(self, nvim):
        self.nvim = nvim
        self.initialized = False
        self.qflist = []
        self.errors = ''
        self.server_url = 'http://localhost:{}'.format(DEFAULT_PORT)
        self.server_alive = False

    def set_server_port(self, port):
        self.server_url = 'http://localhost:{}'.format(port.strip())

    def initialize(self):
        if not self.initialized:
            self.nvim.command('highlight link ScalavistaUnderlineStyle SpellBad')
            self.nvim.command('highlight ScalavistaErrorStyle ctermfg=1 ctermbg=0 guifg=#EC5f67 guibg=#1B2B34')
            self.nvim.command('highlight ScalavistaWarningStyle ctermfg=9 ctermbg=0 guifg=#F99157 guibg=#1B2B34')
            self.nvim.command('set omnifunc=ScalavistaCompleteFunc')
            # self.nvim.command('set completeopt=longest,menuone')
            self.error_sign = 'ScalavistaErrorSign'
            self.warning_sign = 'ScalavistaWarningSign'
            self.info_sign = 'ScalavistaInfoSign'
            self.nvim.command('sign define {} text=!! texthl=ScalavistaErrorStyle'.format(self.error_sign))
            self.nvim.command('sign define {} text=! texthl=ScalavistaWarningStyle'.format(self.warning_sign))
            self.nvim.command('sign define {} text=>'.format(self.info_sign))
            self.nvim.call('timer_start', 500,
                           'ScalavistaRefresh', {'repeat': -1})
            self.initialized = True
            self.check_health()

    def notify(self, msg):
        self.nvim.out_write('scalavista> {}\n'.format(msg))

    def error(self, msg):
        self.nvim.out_write('scalavista> {}\n'.format(msg))

    def check_health(self):
        try:
            req = requests.get(self.server_url + '/alive')
            if req.status_code == requests.codes.ok:
                self.server_alive = True
        except Exception:
            self.server_alive = False

    def find_buffer_from_absfilepath(self, absfilepath):
        buffers = self.nvim.buffers
        for buffer in buffers:
            if absfilepath.endswith(buffer.name):
                return buffer
        raise RuntimeError('failed to find buffer containing {}'.format(absfilepath))

    def reload_current_buffer(self):
        if not self.server_alive:
            return
        absfilepath = self.nvim.call('expand', '%:p')
        if not absfilepath.endswith('.scala'):
            return  # only want to load scala source files.
        buf = self.find_buffer_from_absfilepath(absfilepath)  # self.nvim.current.buffer
        content = '\n'.join(buf)
        data = {'filename': absfilepath, 'fileContents': content}
        try:
            r = requests.post(self.server_url + '/reload-file', json=data)
            if r.status_code != requests.codes.ok:
                self.error('failed to reload buffer')
        except Exception as e:
            self.error('failed to reload buffer: {}'.format(e))

    def update_errors_and_populate_quickfix(self):
        if not self.server_alive:
            return
        mode = self.nvim.api.get_mode()['mode']
        if mode == 'i':
            return  # don't update errors when in insert mode
        try:
            response = requests.get(self.server_url + '/errors')
            new_errors = response.json()
            if (str(new_errors) == str(self.errors)):
                return
            self.errors = new_errors
        except Exception:
            # self.error('failed to get errors')
            pass
        else:
            self.nvim.call('clearmatches')
            self.nvim.command('sign unplace *')
            qflist = []
            infos = []
            warnings = []
            errors = []
            lines = []
            for i, error in enumerate(self.errors):
                path, lnum, col, start, end, text, severity = error
                n_bytes = (int(end) - int(start)) // 2
                lines.append([int(lnum), int(col), n_bytes + 1])
                qflist.append({'filename': path, 'lnum': int(lnum),
                               'text': severity + ':' + text})
                if severity == 'ERROR':
                    errors.append((lnum, path))
                elif severity == 'WARNING':
                    warnings.append((lnum, path))
                else:
                    infos.append((lnum, path))

            sign_idx = 1
            for msgs, sign in [(infos, self.info_sign), (warnings, self.warning_sign), (errors, self.error_sign)]:
                for lnum, path in msgs:
                    try:
                        self.nvim.command('sign place {} line={} name={} file={}'.format(sign_idx, lnum, sign, path))
                    except Exception:
                        pass
                    sign_idx += 1

            self.nvim.call('setqflist', qflist)
            self.nvim.command('let w:quickfix_title="neovim-scala"')
            self.nvim.call('matchaddpos', 'ScalavistaUnderlineStyle', lines)
            self.qflist = self.nvim.call('getqflist')
            # self.nvim.command('cw')
            # self.nvim.command('wincmd p')

    def get_completion(self, completion_type='type'):
        if not self.server_alive:
            return []
        window = self.nvim.current.window
        cursor = window.cursor
        buf = self.nvim.current.buffer
        offset = get_offset_from_cursor(buf[:], cursor)
        content = '\n'.join(buf)
        file_name = self.nvim.call('expand', '%:p')
        data = {'filename': file_name, 'fileContents': content,
                'offset': offset}
        resp = requests.post(self.server_url + '/{}-completion'.format(completion_type), json=data)
        if resp.status_code == requests.codes.ok:
            res = []
            for word, menu in resp.json():
                res.append({'word': word, 'menu': menu, 'dup': 1})
            return res
        self.error('failed to get {} completion'.format(completion_type))
        return []

    @pynvim.function('ScalavistaRefresh')
    def update_errors(self, timer):
        self.check_health()
        # self.reload_current_buffer()
        self.update_errors_and_populate_quickfix()

    @pynvim.function('ScalavistaCompleteFunc', sync=True)
    def scala_complete_func(self, findstart_and_base):
        findstart = findstart_and_base[0]
        base = findstart_and_base[1]

        def detect_row_column_start():
            cursor = self.nvim.current.window.cursor
            row = cursor[0]
            col = cursor[1]
            line = self.nvim.current.line
            startcol = col
            while startcol > 0 and line[startcol - 1] not in " .,([{":
                startcol -= 1
            return row, col, startcol if startcol else 1

        if str(findstart) == '1':
            row, col, startcol = detect_row_column_start()
            return startcol
        else:
            type_completion = self.get_completion('type') + self.get_completion('scope')
            return [comp for comp in type_completion if comp['word'].startswith(base)]

    @pynvim.command('ScalavistaType')
    def get_type(self):
        if not self.server_alive:
            return
        window = self.nvim.current.window
        cursor = window.cursor
        buf = self.nvim.current.buffer
        offset = get_offset_from_cursor(buf[:], cursor)
        content = '\n'.join(buf)
        file_name = self.nvim.call('expand', '%:p')
        data = {'filename': file_name, 'fileContents': content,
                'offset': offset}
        resp = requests.post(self.server_url + '/ask-type-at', json=data)
        if resp.status_code == requests.codes.ok:
            self.nvim.out_write(resp.text + '\n')
        else:
            self.error('failed to get type')

    @pynvim.command('ScalavistaGoto')
    def get_pos(self):
        if not self.server_alive:
            return
        window = self.nvim.current.window
        cursor = window.cursor
        buf = self.nvim.current.buffer
        offset = get_offset_from_cursor(buf[:], cursor)
        content = '\n'.join(buf)
        current_file = self.nvim.call('expand', '%:p')
        data = {'filename': current_file, 'fileContents': content,
                'offset': offset}
        resp = requests.post(self.server_url + '/ask-pos-at', json=data)
        if resp.status_code == requests.codes.ok:
            file = resp.json()['file']
            line = resp.json()['line']
            col = resp.json()['column']
            symbol = resp.json()['symbol']
            if file and file != "<no source file>":
                try:
                    if file != current_file:
                        self.nvim.command('edit {}'.format(file))
                    self.nvim.call('cursor', line, col)
                    # self.notify('jumped to definition of {}'.format(symbol))
                except Exception as e:
                    self.error(e)
            else:
                self.error('unable to find definition of {}'.format(symbol))
        else:
            self.error('goto failed')

    @pynvim.command('ScalavistaDoc')
    def get_doc(self):
        if not self.server_alive:
            return
        window = self.nvim.current.window
        cursor = window.cursor
        buf = self.nvim.current.buffer
        offset = get_offset_from_cursor(buf[:], cursor)
        content = '\n'.join(buf)
        current_file = self.nvim.call('expand', '%:p')
        data = {'filename': current_file, 'fileContents': content,
                'offset': offset}
        resp = requests.post(self.server_url + '/ask-doc-at', json=data)
        if resp.status_code == requests.codes.ok:
            self.notify(resp.text)
        else:
            self.error('failed to find doc')

    @pynvim.command('ScalavistaErrors')
    def scala_errors(self):
        self.update_errors_and_populate_quickfix()

    @pynvim.command('ScalavistaSetPort', nargs='1')
    def set_port(self, args):
        self.set_server_port(args[0])
        self.check_health()

    @pynvim.command('ScalavistaHealth')
    def scalavista_healthcheck(self):
        self.check_health()
        if self.server_alive:
            self.notify('scalavista server at {} is alive!'.format(self.server_url))
        else:
            self.error('unable to connect to scalavista server at {}'.format(self.server_url))

    @pynvim.autocmd('BufEnter', pattern='*.scala', eval='expand("<afile>")', sync=True)
    def on_buf_enter(self, filename):
        self.initialize()
        self.reload_current_buffer()

    @pynvim.autocmd('BufLeave', pattern='*.scala', eval='expand("<afile>")', sync=True)
    def on_buf_leave(self, filename):
        self.reload_current_buffer()

    @pynvim.autocmd('TextChanged', pattern='*.scala')
    def on_text_changed(self):
        self.reload_current_buffer()

    @pynvim.autocmd('TextChangedI', pattern='*.scala')
    def on_text_changed_i(self):
        self.reload_current_buffer()

    @pynvim.autocmd('CursorMoved', pattern='*.scala')
    def on_cursor_moved(self):
        line_num = self.nvim.current.window.cursor[0]
        buf_num = self.nvim.current.buffer.number
        messages = []
        for item in self.qflist:
            if (item['bufnr'] == buf_num) and (item['lnum'] == line_num):
                messages.append(item['text'])
        self.nvim.out_write(' | '.join(messages) + '\n')
