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
class ScalaVim(object):

    def __init__(self, nvim):
        self.nvim = nvim
        self.initialized = False

    def initialize(self):
        if not self.initialized:
            self.nvim.command('highlight ScalaErrorStyle ctermbg=red gui=underline')
            self.nvim.command('set omnifunc=ScalaCompleteFunc')
            self.nvim.command('set completeopt=longest,menuone')
            self.nvim.call('timer_start', 1000,
                           'ScalaUpdateErrors', {'repeat': -1})
            self.initialized = True

    def notify(self, msg):
        self.nvim.out_write('scala-neovim> {}\n'.format(msg))

    def reload_current_buffer(self):
        buf = self.nvim.current.buffer
        content = '\n'.join(buf)
        data = {'filename': buf.name, 'fileContents': content}
        try:
            r = requests.post('http://localhost:8080/reload-file', json=data)
            if r.status_code != requests.codes.ok:
                self.notify('failed to reload buffer')
        except Exception:
            self.notify('failed to reload buffer')

    def update_errors_and_populate_quickfix(self):
        try:
            response = requests.get('http://localhost:8080/errors')
            errors = response.json()
        except Exception:
            self.notify('failed to get errors')
        else:
            self.nvim.call('clearmatches')
            qflist = []
            lines = []
            for error in errors:
                path, lnum, text, severity = error
                lines.append(int(lnum))
                qflist.append({'filename': path, 'lnum': int(lnum),
                               'text': text})
            self.nvim.call('setqflist', qflist)
            self.nvim.call('matchaddpos', 'ScalaErrorStyle', lines)
            # self.nvim.command('cw')
            # self.nvim.command('wincmd p')

    def get_completion(self, completion='type'):
        window = self.nvim.current.window
        cursor = window.cursor
        buf = self.nvim.current.buffer
        offset = get_offset_from_cursor(buf[:], cursor)
        content = '\n'.join(buf)
        data = {'filename': buf.name, 'fileContents': content,
                'offset': offset}
        resp = requests.post('http://localhost:8080/{}-completion'.format(completion), json=data)
        if resp.status_code == requests.codes.ok:
            res = []
            for word, menu in resp.json():
                res.append({'word': word, 'menu': menu})
            return res
        self.notify('failed to get type')
        return []

    @neovim.function('ScalaUpdateErrors')
    def update_errors(self, timer):
        self.update_errors_and_populate_quickfix()

    @neovim.function('ScalaCompleteFunc', sync=True)
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
            type_completion = self.get_completion('type')
            if type_completion:
                return type_completion
            return self.get_completion('scope')

    @neovim.command('ScalaType')
    def get_type(self):
        window = self.nvim.current.window
        cursor = window.cursor
        buf = self.nvim.current.buffer
        offset = get_offset_from_cursor(buf[:], cursor)
        content = '\n'.join(buf)
        data = {'filename': buf.name, 'fileContents': content,
                'offset': offset}
        resp = requests.post('http://localhost:8080/ask-type-at', json=data)
        if resp.status_code == requests.codes.ok:
            self.nvim.out_write(resp.text + '\n')
        else:
            self.notify('failed to get type')

    @neovim.command('ScalaErrors')
    def scala_errors(self):
        self.update_errors_and_populate_quickfix()

    # @neovim.command('ScalaCompleteScope')
    # def get_scope_completion(self):
    #     window = self.nvim.current.window
    #     cursor = window.cursor
    #     buf = self.nvim.current.buffer
    #     offset = get_offset_from_cursor(buf[:], cursor)
    #     members = self.engine.askScopeCompletion('current_buffer',
    #                                              '\n'.join(buf), offset)
    #     # self.nvim.out_write(members)

    # @neovim.autocmd('CursorHold', pattern='*.scala')
    # def on_cursor_hold(self):
    #     self.update_errors_and_populate_quickfix()

    # @neovim.autocmd('CursorHoldI', pattern='*.scala')
    # def on_cursor_hold_i(self):
    #     self.update_errors_and_populate_quickfix()

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

    # @neovim.command('TestCommand', nargs='*', range='')
    # def testcommand(self, args, range):
    #     self.nvim.current.line = ('Command with args: {}, range: {}'
    #                              .format(args, range))
