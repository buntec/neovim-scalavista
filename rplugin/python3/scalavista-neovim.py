import json
import os
import re
import random
import inspect
import uuid
import requests
import pynvim
from packaging.version import Version


MIN_PORT = 49152
MAX_PORT = 65535


def get_offset_from_cursor(buf, cursor):
    line = cursor[0]
    col = cursor[1]
    offset = 0
    for i in range(line - 1):
        offset += len(buf[i]) + 1
    offset += col
    return offset


# used to download server jars
def download_file(url, file_name):
    with open(file_name, "wb") as file:
        response = requests.get(url)
        file.write(response.content)


def is_valid_server_jar(jar):
    scalavista_version_pattern = re.compile(r"\d+\.\d+\.\d+")
    scala_version_pattern = re.compile(r"_\d\.\d{1,2}\.jar")
    overall_pattern = re.compile(r"scalavista-server-.*\.jar")
    return (
        scala_version_pattern.search(jar) is not None
        and scalavista_version_pattern.search(jar) is not None
        and overall_pattern.search(jar) is not None
    )


def get_scala_version_from_server_jar(jar):
    scala_version_pattern = re.compile(r"_(\d\.\d{1,2})\.jar")
    return scala_version_pattern.search(jar)[1]


def get_scalavista_version_from_server_jar(jar):
    scalavista_version_pattern = re.compile(r"\d+\.\d+\.\d+")
    return scalavista_version_pattern.search(jar)[0]


def get_latest_server_version(self):
    releases = requests.get(
        "https://api.github.com/repos/buntec/scalavista-server/releases"
    ).json()
    return releases[0]["tag_name"][1:]


@pynvim.plugin
class Scalavista(object):
    def __init__(self, nvim):
        self.nvim = nvim
        self.initialized = False
        self.qflist = []
        self.errors = ""
        self.server_port = random.randint(MIN_PORT, MAX_PORT)
        self.server_alive = False
        self.try_to_start_server = True
        self.uuid = uuid.uuid4().hex

    def get_plugin_path(self):
        runtime_paths = self.nvim.list_runtime_paths()
        for path in runtime_paths:
            if path.find("neovim-scalavista") > -1:
                return path
        raise RuntimeError("neovim-scalavista runtime path not found")

    def server_url(self):
        return "http://localhost:{}".format(self.server_port)

    @pynvim.command("ScalavistaCommands")
    def show_commands(self):
        def predicate(fn):
            return hasattr(fn, "_nvim_rpc_method_name") and getattr(
                fn, "_nvim_rpc_method_name"
            ).startswith("command:")

        for name, fn in inspect.getmembers(self, predicate):
            command_name = getattr(fn, "_nvim_rpc_method_name").lstrip('command:')
            self.notify(command_name)

    @pynvim.command("ScalavistaServerJars")
    def print_server_jars(self):
        self.locate_server_jars()
        self.notify(self.locate_server_jars())

    def locate_server_jars(self):
        runtime_paths = self.nvim.list_runtime_paths()
        server_jars = []
        for path in ["."] + runtime_paths:
            if os.path.isdir(path):
                for file in os.listdir(path):
                    if is_valid_server_jar(file):
                        server_jars.append(os.path.join(path, file))
        server_jars_by_version = {}
        for jar in server_jars:
            version = get_scalavista_version_from_server_jar(jar)
            if version not in server_jars_by_version:
                server_jars_by_version[version] = [jar]
            else:
                server_jars_by_version[version].append(jar)
        if not server_jars_by_version:
            return {}
        all_versions = [Version(v) for v in server_jars_by_version.keys()]
        all_versions.sort()
        latest_version = all_versions[-1]
        latest_server_jars = server_jars_by_version[latest_version.public]
        server_jars_by_scala_version = {}
        for jar in latest_server_jars:
            scala_version = get_scala_version_from_server_jar(jar)
            server_jars_by_scala_version[scala_version] = jar
        return server_jars_by_scala_version

    def initialize(self):
        if not self.initialized:

            self.locate_server_jars()

            if self.nvim.call("exists", "g:scalavista_default_scala_version"):
                self.default_scala_version = self.nvim.eval(
                    "g:scalavista_default_scala_version"
                )
            else:
                self.default_scala_version = "2.13"

            try:
                cwd = self.nvim.call("getcwd")
                path_to_try = os.path.join(cwd, "scalavista.json")
                with open(path_to_try) as f:
                    self.scala_version = json.load(f)["scalaBinaryVersion"]
                    self.notify(
                        "scalavista.json found - Scala binary version for this project is {}".format(
                            self.scala_version
                        )
                    )
            except Exception:
                self.notify(
                    "scalavista.json not found - defaulting to Scala {}".format(
                        self.default_scala_version
                    )
                )
                self.scala_version = None
                pass

            self.nvim.command("highlight link ScalavistaUnderlineStyle SpellBad")
            self.nvim.command(
                "highlight ScalavistaErrorStyle ctermfg=1 ctermbg=0 guifg=#EC5f67 guibg=#1B2B34"
            )
            self.nvim.command(
                "highlight ScalavistaWarningStyle ctermfg=9 ctermbg=0 guifg=#F99157 guibg=#1B2B34"
            )
            self.nvim.command("set omnifunc=ScalavistaCompleteFunc")
            # self.nvim.command('set completeopt=longest,menuone')  # better let the user set this
            self.error_sign = "ScalavistaErrorSign"
            self.warning_sign = "ScalavistaWarningSign"
            self.info_sign = "ScalavistaInfoSign"
            self.nvim.command(
                "sign define {} text=!! texthl=ScalavistaErrorStyle".format(
                    self.error_sign
                )
            )
            self.nvim.command(
                "sign define {} text=! texthl=ScalavistaWarningStyle".format(
                    self.warning_sign
                )
            )
            self.nvim.command("sign define {} text=>".format(self.info_sign))
            self.refresh_timer = self.nvim.call(
                "timer_start", 500, "ScalavistaRefresh", {"repeat": -1}
            )
            self.server_start_timer = self.nvim.call(
                "timer_start", 500, "ScalavistaConditionallyStartServer", {"repeat": -1}
            )
            self.initialized = True
            self.check_health()

    def get_scala_version(self):
        if self.scala_version is not None:
            return self.scala_version
        else:
            return self.default_scala_version

    def notify(self, msg):
        self.nvim.out_write("scalavista[info]> {}\n".format(msg))

    def warn(self, msg):
        self.nvim.out_write("scalavista[warn]> {}\n".format(msg))

    def error(self, msg):
        self.nvim.out_write("scalavista[error]> {}\n".format(msg))

    @pynvim.command("ScalavistaDownloadServerJars")
    def download_server_jars(self):
        try:
            releases = requests.get(
                "https://api.github.com/repos/buntec/scalavista-server/releases"
            ).json()
        except Exception:
            self.error(
                "failed to query github for latest server releases - no internet or behind proxy?"
            )
        else:
            for asset in releases[0]["assets"]:
                name = asset["name"]
                if is_valid_server_jar(name):
                    download_url = asset["browser_download_url"]
                    self.notify("attempting to download {} ...".format(download_url))
                    write_path = os.path.join(self.get_plugin_path(), name)
                    download_file(download_url, write_path)
                    self.notify(
                        "successfully downloaded {} to {}".format(name, write_path)
                    )

    # @pynvim.command("ScalavistaStartServer")
    def start_server(self, server_jar):
        self.try_to_start_server = False
        self.server_job = self.nvim.call(
            "jobstart",
            [
                "java",
                "-jar",
                server_jar,
                "--uuid",
                self.uuid,
                "--port",
                self.server_port,
            ],
            {"on_exit": "ScalavistaServerFailed"},
        )
        if self.server_job > 0:
            self.notify("starting scalavista server from {}".format(server_jar))
        else:
            self.error("failed to start scalavista server from {}".format(server_jar))

    @pynvim.command("ScalavistaRestartServer")
    def stop_server(self):
        try:
            self.nvim.call("chansend", self.server_job, ["x", ""])
            self.nvim.call("jobstop", self.server_job)
        except Exception:
            pass

    @pynvim.function("ScalavistaServerFailed")
    def resume_server_start(self, code):
        self.warn("scalavista server exited - will try to restart...".format(code))
        self.try_to_start_server = True

    @pynvim.function("ScalavistaConditionallyStartServer")
    def conditionally_start_server(self, timer):
        if (
            self.try_to_start_server and not self.server_alive
        ):
            scalavista_server_jars = self.locate_server_jars()
            scala_version = self.get_scala_version()
            if scala_version in scalavista_server_jars:
                server_jar = scalavista_server_jars[scala_version]
                self.server_port = random.randint(MIN_PORT, MAX_PORT)
                self.start_server(server_jar)

    def check_health(self):
        try:
            res = requests.get(self.server_url() + "/alive")
            if res.status_code == requests.codes.ok and res.text == self.uuid:
                if not self.server_alive:
                    version = self.get_server_version()
                    self.notify(
                        "scalavista server {} now live at {}".format(
                            version, self.server_url()
                        )
                    )
                self.server_alive = True
            else:
                raise Exception("uuid mismatch or bad server response: {}".format(res))
        except Exception:
            self.server_alive = False

    def get_server_version(self):
        try:
            response = requests.get(self.server_url() + "/version")
            return response.text
        except Exception:
            self.error("failed to get scalavista server version")
            return "?"

    def server_version_is_outdated(self):
        try:
            latest_version = self.get_latest_server_version()
            response = requests.get(self.server_url() + "/version")
            return (response.status_code != requests.codes.ok) or Version(
                latest_version
            ) > Version(response.text)
        except Exception:
            return False

    def find_buffer_from_absfilepath(self, absfilepath):
        buffers = self.nvim.buffers
        for buffer in buffers:
            if absfilepath.endswith(buffer.name):
                return buffer
        raise RuntimeError("failed to find buffer containing {}".format(absfilepath))

    def reload_current_buffer(self):
        if not self.server_alive:
            return
        absfilepath = self.nvim.call("expand", "%:p")
        # if not absfilepath.endswith('.scala'):
        #     return  # only want to load scala source files.
        buf = self.find_buffer_from_absfilepath(absfilepath)  # self.nvim.current.buffer
        content = "\n".join(buf)
        data = {"filename": absfilepath, "fileContents": content}
        try:
            r = requests.post(self.server_url() + "/reload-file", json=data)
            if r.status_code != requests.codes.ok:
                self.error("failed to reload buffer")
        except Exception as e:
            self.error("failed to reload buffer: {}".format(e))

    def update_errors_and_populate_quickfix(self):
        if not self.server_alive:
            return
        mode = self.nvim.api.get_mode()["mode"]
        if mode == "i":
            return  # don't update errors when in insert mode
        try:
            response = requests.get(self.server_url() + "/errors")
            new_errors = response.json()
            if str(new_errors) == str(self.errors):
                return
            self.errors = new_errors
        except Exception:
            # self.error('failed to get errors')
            pass
        else:
            self.nvim.call("clearmatches")
            self.nvim.command("sign unplace *")
            qflist = []
            infos = []
            warnings = []
            errors = []
            lines = []
            for i, error in enumerate(self.errors):
                path, lnum, col, start, end, text, severity = error
                n_bytes = (int(end) - int(start)) // 2
                lines.append([int(lnum), int(col), n_bytes + 1])
                qflist.append(
                    {"filename": path, "lnum": int(lnum), "text": severity + ":" + text}
                )
                if severity == "ERROR":
                    errors.append((lnum, path))
                elif severity == "WARNING":
                    warnings.append((lnum, path))
                else:
                    infos.append((lnum, path))

            sign_idx = 1
            for msgs, sign in [
                (infos, self.info_sign),
                (warnings, self.warning_sign),
                (errors, self.error_sign),
            ]:
                for lnum, path in msgs:
                    try:
                        self.nvim.command(
                            "sign place {} line={} name={} file={}".format(
                                sign_idx, lnum, sign, path
                            )
                        )
                    except Exception:
                        pass
                    sign_idx += 1

            self.nvim.call("setqflist", qflist)
            self.nvim.command('let w:quickfix_title="neovim-scalavista"')
            self.nvim.call("matchaddpos", "ScalavistaUnderlineStyle", lines)
            self.qflist = self.nvim.call("getqflist")
            # self.nvim.command('cw')
            # self.nvim.command('wincmd p')

    def get_completion(self, completion_type="type"):
        if not self.server_alive:
            return []
        window = self.nvim.current.window
        cursor = window.cursor
        buf = self.nvim.current.buffer
        offset = get_offset_from_cursor(buf[:], cursor)
        content = "\n".join(buf)
        file_name = self.nvim.call("expand", "%:p")
        data = {"filename": file_name, "fileContents": content, "offset": offset}
        resp = requests.post(
            self.server_url() + "/{}-completion".format(completion_type), json=data
        )
        if resp.status_code == requests.codes.ok:
            res = []
            for word, menu in resp.json():
                res.append({"word": word, "menu": menu, "dup": 1})
            return res
        self.error("failed to get {} completion".format(completion_type))
        return []

    @pynvim.function("ScalavistaRefresh")
    def update_errors(self, timer):
        self.check_health()
        self.update_errors_and_populate_quickfix()

    @pynvim.function("ScalavistaCompleteFunc", sync=True)
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

        if str(findstart) == "1":
            row, col, startcol = detect_row_column_start()
            return startcol
        else:
            type_completion = self.get_completion("type") + self.get_completion("scope")
            return [comp for comp in type_completion if comp["word"].startswith(base)]

    @pynvim.command("ScalavistaType")
    def get_type(self):
        if not self.server_alive:
            return
        window = self.nvim.current.window
        cursor = window.cursor
        buf = self.nvim.current.buffer
        offset = get_offset_from_cursor(buf[:], cursor)
        content = "\n".join(buf)
        file_name = self.nvim.call("expand", "%:p")
        data = {"filename": file_name, "fileContents": content, "offset": offset}
        resp = requests.post(self.server_url() + "/ask-type-at", json=data)
        if resp.status_code == requests.codes.ok:
            self.nvim.out_write(resp.text + "\n")
        else:
            self.error("failed to get type")

    @pynvim.command("ScalavistaGoto")
    def get_pos(self):
        if not self.server_alive:
            return
        window = self.nvim.current.window
        cursor = window.cursor
        buf = self.nvim.current.buffer
        offset = get_offset_from_cursor(buf[:], cursor)
        content = "\n".join(buf)
        current_file = self.nvim.call("expand", "%:p")
        data = {"filename": current_file, "fileContents": content, "offset": offset}
        resp = requests.post(self.server_url() + "/ask-pos-at", json=data)
        if resp.status_code == requests.codes.ok:
            file = resp.json()["file"]
            line = resp.json()["line"]
            col = resp.json()["column"]
            symbol = resp.json()["symbol"]
            if file and file != "<no source file>":
                try:
                    if (file != current_file) and (file != "<no file>"):
                        self.nvim.command("edit {}".format(file))
                    self.nvim.call("cursor", line, col)
                    # self.notify('jumped to definition of {}'.format(symbol))
                except Exception as e:
                    self.error(e)
            else:
                self.error("unable to find definition of {}".format(symbol))
        else:
            self.error("goto failed")

    @pynvim.command("ScalavistaDoc")
    def get_doc(self):
        if not self.server_alive:
            return
        window = self.nvim.current.window
        cursor = window.cursor
        buf = self.nvim.current.buffer
        offset = get_offset_from_cursor(buf[:], cursor)
        content = "\n".join(buf)
        current_file = self.nvim.call("expand", "%:p")
        data = {"filename": current_file, "fileContents": content, "offset": offset}
        resp = requests.post(self.server_url() + "/ask-doc-at", json=data)
        if resp.status_code == requests.codes.ok:
            doc_string = resp.text
            if not doc_string:
                self.error("no scaladoc found")
                return
            # current_buffer_name = self.nvim.call('bufname', '%')
            self.nvim.command('let help = "{}"'.format(doc_string))
            self.nvim.command("botright 12 new")
            self.nvim.command("edit {}".format("scalavista-scaladoc"))
            self.nvim.command("setlocal bufhidden=wipe")
            self.nvim.command("setlocal nobuflisted")
            self.nvim.command("setlocal buftype=nofile")
            self.nvim.command("setlocal noswapfile")
            self.nvim.command("setlocal nospell")
            self.nvim.command("0 put =help")
            # self.nvim.command('buffer {}'.format(current_buffer_name))
        else:
            self.error("failed to retrieve scaladoc")

    @pynvim.command("ScalavistaErrors")
    def scala_errors(self):
        self.update_errors_and_populate_quickfix()

    @pynvim.command("ScalavistaHealth")
    def scalavista_healthcheck(self):
        self.check_health()
        if self.server_alive:
            server_version = self.get_server_version()
            self.notify(
                "scalavista server version {} at {} is alive".format(
                    server_version, self.server_url()
                )
            )
        else:
            self.error(
                "unable to connect to scalavista server at {}".format(self.server_url())
            )
        if self.server_version_is_outdated():
            self.notify(
                "your scalavista server version is outdated - please update by running :ScalavistaDownloadServerJars"
            )

    @pynvim.autocmd(
        "BufEnter", pattern="*.scala,*.java", eval='expand("<afile>")', sync=True
    )
    def on_buf_enter(self, filename):
        self.initialize()
        self.reload_current_buffer()

    @pynvim.autocmd(
        "BufLeave", pattern="*.scala,*.java", eval='expand("<afile>")', sync=True
    )
    def on_buf_leave(self, filename):
        self.reload_current_buffer()

    @pynvim.autocmd(
        "VimLeavePre", pattern="*.scala,*.java", eval='expand("<afile>")', sync=True
    )
    def on_vim_leave(self, filename):
        self.nvim.call("timer_stop", self.refresh_timer)
        self.nvim.call("timer_stop", self.server_start_timer)
        # the next line is a hack: when we exit nvim then 'on_exit' is called
        # on the server process, but the 'ScalavistaServerFailed' callback
        # is a rpc whose channel no longer exist so we have to overwrite the
        # function with a no-op.
        self.nvim.command("function! ScalavistaServerFailed(a, b, c)\nendfunction")
        self.stop_server()

    @pynvim.autocmd("TextChanged", pattern="*.scala,*.java")
    def on_text_changed(self):
        self.reload_current_buffer()

    @pynvim.autocmd("TextChangedI", pattern="*.scala,*.java")
    def on_text_changed_i(self):
        self.reload_current_buffer()

    @pynvim.autocmd("CursorMoved", pattern="*.scala,*.java")
    def on_cursor_moved(self):
        line_num = self.nvim.current.window.cursor[0]
        buf_num = self.nvim.current.buffer.number
        messages = []
        for item in self.qflist:
            if (item["bufnr"] == buf_num) and (item["lnum"] == line_num):
                messages.append(item["text"])
        self.nvim.out_write(" | ".join(messages) + "\n")
