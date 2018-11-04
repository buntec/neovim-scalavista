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

    @neovim.command('ScalaType')
    def get_type(self):
        window = self.nvim.current.window
        cursor = window.cursor
        buf = self.nvim.current.buffer
        offset = get_offset_from_cursor(buf[:], cursor)
        tpe = self.engine.askTypeAt('current_buffer', '\n'.join(buf), offset)
        self.nvim.out_write(tpe + '\n')

    @neovim.command('ScalaErrors')
    def get_errors(self):
        errors = self.engine.getErrors()
        self.nvim.err_write(errors + '\n')

    @neovim.autocmd('BufEnter', pattern='*.scala')
    def on_buf_enter(self):
        self._initialize()

    @neovim.autocmd('BufWritePost', pattern='*.scala')
    def after_buffer_write(self):
        buf = self.nvim.current.buffer
        self.engine.reloadFile('current_buffer', '\n'.join(buf))

    @neovim.command('TestCommand', nargs='*', range='')
    def testcommand(self, args, range):
        self.nvim.current.line = ('Command with args: {}, range: {}'
                                  .format(args, range))
