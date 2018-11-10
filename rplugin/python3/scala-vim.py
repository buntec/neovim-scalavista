from py4j.java_gateway import JavaGateway

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
        self.gateway = None
        self.engine = None

    def _initialize(self):
        if self.gateway is None:
            try:
                self.gateway = JavaGateway()
                self.engine = self.gateway.entry_point
            except Exception:
                self.nvim.err_write('scala-vim: failed to connect'
                                    'to completion engine...' + '\n')
        self.nvim.call('timer_start', 500, 'ScalaUpdateErrors', {'repeat': -1})

    @neovim.function('ScalaUpdateErrors')
    def update_errors(self, timer):
        self.update_errors_and_populate_quickfix()

    def reload_buffer(self):
        buf = self.nvim.current.buffer
        self.engine.reloadFile('current_buffer', '\n'.join(buf))

    def update_errors_and_populate_quickfix(self):
        errors = self.engine.getErrors()
        # self.nvim.out_write(str(errors) + '\n')
        qflist = []
        for error in errors:
            lnum, text, severity = error.split(';')
            qflist.append({'bufnr': 1, 'lnum': int(lnum), 'text': text})
        self.nvim.call('setqflist', qflist)
        # self.nvim.command('cw')
        # self.nvim.command('wincmd p')

    @neovim.command('ScalaType')
    def get_type(self):
        window = self.nvim.current.window
        cursor = window.cursor
        buf = self.nvim.current.buffer
        offset = get_offset_from_cursor(buf[:], cursor)
        tpe = self.engine.askTypeAt('current_buffer', '\n'.join(buf), offset)
        self.nvim.out_write(tpe + '\n')

    @neovim.command('ScalaCompleteType')
    def get_type_completion(self):
        window = self.nvim.current.window
        cursor = window.cursor
        buf = self.nvim.current.buffer
        offset = get_offset_from_cursor(buf[:], cursor)
        members = self.engine.askTypeCompletion('current_buffer',
                                                '\n'.join(buf), offset)
        # self.nvim.out_write(members)

    @neovim.command('ScalaCompleteScope')
    def get_scope_completion(self):
        window = self.nvim.current.window
        cursor = window.cursor
        buf = self.nvim.current.buffer
        offset = get_offset_from_cursor(buf[:], cursor)
        members = self.engine.askScopeCompletion('current_buffer',
                                                 '\n'.join(buf), offset)
        # self.nvim.out_write(members)


    #@neovim.autocmd('CursorHold', pattern='*.scala')
    #def on_cursor_hold(self):
    #    self.update_errors_and_populate_quickfix()

    #@neovim.autocmd('CursorHoldI', pattern='*.scala')
    #def on_cursor_hold_i(self):
    #    self.update_errors_and_populate_quickfix()

    @neovim.autocmd('BufEnter', pattern='*.scala')
    def on_buf_enter(self):
        self._initialize()

    @neovim.autocmd('TextChanged', pattern='*.scala')
    def on_text_changed(self):
        self.nvim.out_write('text changed triggered')
        self.reload_buffer()

    @neovim.autocmd('TextChangedI', pattern='*.scala')
    def on_text_changed_i(self):
        self.nvim.out_write('text changed i triggered')
        self.reload_buffer()

    @neovim.command('TestCommand', nargs='*', range='')
    def testcommand(self, args, range):
        self.nvim.current.line = ('Command with args: {}, range: {}'
                                  .format(args, range))
