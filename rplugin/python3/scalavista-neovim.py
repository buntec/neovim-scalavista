import requests
import neovim


def get_offset_from_cursor(buf, cursor):
    line = cursor[0]
    col = cursor[1]
    offset = 0
    for i in range(line - 1):
        offset += len(buf[i]) + 1
    offset += col
    return offset


@neovim.plugin
class Scalavista(object):

    def __init__(self, nvim):
        self.nvim = nvim
        self.initialized = False
        self.qflist = []
        self.server_url = 'http://localhost:9317'

    def set_server_url(self, port):
        self.server_url = 'http://localhost:{}'.format(port.strip())

    def initialize(self):
        if not self.initialized:
            self.nvim.command('highlight ScalavistaErrorStyle ctermbg=red gui=underline')
            self.nvim.command('set omnifunc=ScalavistaCompleteFunc')
            # self.nvim.command('set completeopt=longest,menuone')
            self.nvim.call('timer_start', 1000,
                           'ScalavistaUpdateErrors', {'repeat': -1})
            self.initialized = True

    def notify(self, msg):
        self.nvim.out_write('scalavista> {}\n'.format(msg))

    def error(self, msg):
        self.nvim.out_write('scalavista> {}\n'.format(msg))

    def reload_current_buffer(self):
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
        try:
            response = requests.get(self.server_url + '/errors')
            errors = response.json()
        except Exception:
            # self.error('failed to get errors')
            pass
        else:
            self.nvim.call('clearmatches')
            qflist = []
            lines = []
            for error in errors:
                path, lnum, text, severity = error
                lines.append(int(lnum))
                qflist.append({'filename': path, 'lnum': int(lnum),
                               'text': severity + ':' + text})
            self.nvim.call('setqflist', qflist)
            self.nvim.command('let w:quickfix_title="neovim-scala"')
            self.nvim.call('matchaddpos', 'ScalavistaErrorStyle', lines)
            self.qflist = self.nvim.call('getqflist')
            # self.nvim.command('cw')
            # self.nvim.command('wincmd p')

    def get_completion(self, completion='type'):
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

    @neovim.function('ScalavistaUpdateErrors')
    def update_errors(self, timer):
        self.update_errors_and_populate_quickfix()

    @neovim.function('ScalavistaCompleteFunc', sync=True)
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

    @neovim.command('ScalavistaType')
    def get_type(self):
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

    @neovim.command('ScalavistaGoto')
    def get_pos(self):
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
                self.notify('jumped to definition of {}'.format(symbol))
                if file != current_file:
                    self.nvim.command('edit {}'.format(file))
                self.nvim.call('cursor', line, col)
            else:
                self.notify('unable to find definition of {}'.format(symbol))
        else:
            self.error('goto failed')

    @neovim.command('ScalavistaErrors')
    def scala_errors(self):
        self.update_errors_and_populate_quickfix()

    @neovim.command('ScalavistaSetPort', nargs='1')
    def set_port(self, args):
        self.set_server_url(args[0])
        self.notify(self.server_url)

    # @neovim.command('ScalavistaCompleteScope')
    # def get_scope_completion(self):
    #     window = self.nvim.current.window
    #     cursor = window.cursor
    #     buf = self.nvim.current.buffer
    #     offset = get_offset_from_cursor(buf[:], cursor)
    #     members = self.engine.askScopeCompletion('current_buffer',
    #                                              '\n'.join(buf), offset)
    #     # self.nvim.out_write(members)

    @neovim.autocmd('BufEnter', pattern='*.scala')
    def on_buf_enter(self):
        self.initialize()
        self.reload_current_buffer()

    @neovim.autocmd('TextChanged', pattern='*.scala')
    def on_text_changed(self):
        # self.nvim.out_write('text changed triggered')
        self.reload_current_buffer()

    @neovim.autocmd('TextChangedI', pattern='*.scala')
    def on_text_changed_i(self):
        # self.nvim.out_write('text changed i triggered')
        self.reload_current_buffer()

    @neovim.autocmd('CursorMoved', pattern='*.scala')
    def on_cursor_moved(self):
        line_num = self.nvim.current.window.cursor[0]
        buf_num = self.nvim.current.buffer.number
        messages = []
        for item in self.qflist:
            if (item['bufnr'] == buf_num) and (item['lnum'] == line_num):
                messages.append(item['text'])
        self.nvim.out_write(' | '.join(messages) + '\n')
