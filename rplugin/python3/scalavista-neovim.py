import requests
import pynvim


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
        self.server_url = 'http://localhost:9317'
        self.server_alive = False

    def set_server_port(self, port):
        self.server_url = 'http://localhost:{}'.format(port.strip())

    def initialize(self):
        if not self.initialized:
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
            self.nvim.call('timer_start', 1000,
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

    def reload_current_buffer(self):
        if not self.server_alive:
            return
        buf = self.nvim.current.buffer
        content = '\n'.join(buf)
        file_name = self.nvim.call('expand', '%:p')
        data = {'filename': file_name, 'fileContents': content}
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
            lines = []
            for i, error in enumerate(self.errors):
                path, lnum, text, severity = error
                lines.append(int(lnum))
                qflist.append({'filename': path, 'lnum': int(lnum),
                               'text': severity + ':' + text})
                if severity == 'ERROR':
                    sign = self.error_sign
                elif severity == 'WARNING':
                    sign = self.warning_sign
                else:
                    sign = self.info_sign
                try:
                    self.nvim.command('sign place {} line={} name={} file={}'.format(i + 1, lnum, sign, path))
                except Exception:
                    pass
            self.nvim.call('setqflist', qflist)
            self.nvim.command('let w:quickfix_title="neovim-scala"')
            # self.nvim.call('matchaddpos', 'ScalavistaErrorStyle', lines)
            self.qflist = self.nvim.call('getqflist')
            # self.nvim.command('cw')
            # self.nvim.command('wincmd p')

    def get_completion(self, completion='type'):
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
        resp = requests.post(self.server_url + '/{}-completion'.format(completion), json=data)
        if resp.status_code == requests.codes.ok:
            res = []
            for word, menu in resp.json():
                res.append({'word': word, 'menu': menu, 'dup': 1})
            return res
        self.error('failed to get type')
        return []

    @pynvim.function('ScalavistaRefresh')
    def update_errors(self, timer):
        self.check_health()
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
                    self.notify('jumped to definition of {}'.format(symbol))
                except Exception as e:
                    self.error(e)
            else:
                self.notify('unable to find definition of {}'.format(symbol))
        else:
            self.error('goto failed')

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

    @pynvim.autocmd('BufEnter', pattern='*.scala')
    def on_buf_enter(self):
        self.initialize()
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
