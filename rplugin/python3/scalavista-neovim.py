import json
import os
import re
import fnmatch
import uuid
import requests
import pynvim


DEFAULT_PORT = 9317
MAX_SERVER_LAUNCH_ATTEMPTS = 10


def get_offset_from_cursor(buf, cursor):
    line = cursor[0]
    col = cursor[1]
    offset = 0
    for i in range(line - 1):
        offset += len(buf[i]) + 1
    offset += col
    return offset


# return true if v1 <= v2
def compare_versions(v1, v2):
    major1, minor1, patch1 = [int(i) for i in v1.split(".")]
    major2, minor2, patch2 = [int(i) for i in v2.split(".")]
    if major1 > major2:
        return False
    if (major1 == major2) and (minor1 > minor2):
        return False
    if (major1 == major2) and (minor1 == minor2) and (patch1 > patch2):
        return False
    return True


# used to download server jars
def download_file(url, file_name):
    with open(file_name, "wb") as file:
        response = requests.get(url)
        file.write(response.content)


class Version:
    def __init__(self, version_string):
        self.major, self.minor, self.patch = [int(i) for i in version_string.split(".")]
        self.from_string = version_string

    def __lt__(self, other):
        if self.major > other.major:
            return False
        if (self.major == other.major) and (self.minor > other.minor):
            return False
        if (
            (self.major == other.major)
            and (self.minor == other.minor)
            and (self.patch >= other.patch)
        ):
            return False
        return True


@pynvim.plugin
class Scalavista(object):
    def __init__(self, nvim):
        self.nvim = nvim
        self.initialized = False
        self.qflist = []
        self.errors = ""
        self.server_port = DEFAULT_PORT
        self.server_alive = False
        self.server_launch_attempts = 0
        self.uuid = uuid.uuid4().hex

    def server_url(self):
        return "http://localhost:{}".format(self.server_port)

    def set_server_port(self, port):
        self.server_port = int(port)

    def get_latest_server_version(self):
        releases = requests.get(
            "https://api.github.com/repos/buntec/scalavista-server/releases"
        ).json()
        return releases[0]["tag_name"][1:]

    @pynvim.command("ScalavistaLocateServerJars")
    def print_server_jars(self):
        self.notify(self.locate_server_jars())

    def locate_server_jars(self):
        runtime_paths = self.nvim.list_runtime_paths()
        server_jars = []
        for path in ["."] + runtime_paths:
            if os.path.isdir(path):
                for file in os.listdir(path):
                    if fnmatch.fnmatch(file, "scalavista-server-*.jar"):
                        server_jars.append(os.path.join(path, file))
        server_jars_by_version = {}
        for jar in server_jars:
            version_match = re.search(r"\d+\.\d+\.\d+", jar)
            if version_match is not None:
                version = version_match[0]
                if version not in server_jars_by_version:
                    server_jars_by_version[version] = [jar]
                else:
                    server_jars_by_version[version].append(jar)
        if not server_jars_by_version:
            return {}
        versions = [Version(v) for v in server_jars_by_version.keys()]
        versions.sort()
        latest_version = versions[-1]
        latest_server_jars = server_jars_by_version[latest_version.from_string]
        server_jars_by_scala_version = {}
        for jar in latest_server_jars:
            scala_version = jar.split("_")[-1].strip(".jar")
            server_jars_by_scala_version[scala_version] = jar
        return server_jars_by_scala_version

    def initialize(self):
        if not self.initialized:

            if self.nvim.call("exists", "g:scalavista_server_jars"):
                self.scalavista_server_jars = self.nvim.eval("g:scalavista_server_jars")
            else:
                self.scalavista_server_jars = self.locate_server_jars()

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

            self.start_server()

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
                "timer_start",
                5000,
                "ScalavistaConditionallyStartServer",
                {"repeat": MAX_SERVER_LAUNCH_ATTEMPTS},
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

    def error(self, msg):
        self.nvim.out_write("scalavista[error]> {}\n".format(msg))

    @pynvim.command("ScalavistaDownloadServerJars")
    def download_server_jars(self):
        releases = requests.get(
            "https://api.github.com/repos/buntec/scalavista-server/releases"
        ).json()
        for asset in releases[0]["assets"]:
            name = asset["name"]
            if name.startswith("scalavista-server") and name.endswith(".jar"):
                download_url = asset["browser_download_url"]
                self.notify("attempting to download {} ...".format(download_url))
                download_file(download_url, name)
                self.notify("successfully downloaded {}".format(name))

    @pynvim.command("ScalavistaStartServer")
    def start_server(self):
        scala_version = self.get_scala_version()
        if scala_version not in self.scalavista_server_jars:
            self.error(
                "no server jar found for Scala version {} - run :ScalavistaDownloadServerJars".format(
                    scala_version
                )
            )
            return
        server_jar = self.scalavista_server_jars[self.get_scala_version()]
        self.server_job = self.nvim.call(
            "jobstart",
            ["java", "-jar", server_jar, "--uuid", self.uuid, "--port", self.server_port],
        )
        if self.server_job > 0:
            self.notify("starting scalavista server from {}".format(server_jar))
        else:
            self.error("failed to start scalavista server from {}".format(server_jar))

    @pynvim.command("ScalavistaStopServer")
    def stop_server(self):
        try:
            self.nvim.call("jobstop", self.server_job)
        except Exception:
            pass

    @pynvim.function("ScalavistaConditionallyStartServer")
    def conditionally_start_server(self, timer):
        if (
            not self.server_alive
            and self.get_scala_version() in self.scalavista_server_jars
        ):
            self.server_port += (
                1
            )  # perhaps another instance with different uuid already serving on this port
            self.start_server()

    def check_health(self):
        try:
            res = requests.get(self.server_url() + "/alive")
            if res.status_code == requests.codes.ok and res.text == self.uuid:
                if not self.server_alive:
                    self.notify(
                        "scalavista server now live at {}".format(self.server_url())
                    )
                self.server_alive = True
            else:
                raise Exception("uuid mismatch or bad server response: {}".format(res))
        except Exception:
            self.server_alive = False

    def get_server_version(self):
        try:
            response = requests.get(self.server_url() + "/version")
            return response.tet
        except Exception:
            self.error("failed to get scalavista server version")
            return "?"

    def server_version_is_outdated(self):
        try:
            latest_version = self.get_latest_server_version()
            response = requests.get(self.server_url() + "/version")
            return (response.status_code != requests.codes.ok) or not compare_versions(
                latest_version, response.text
            )
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

    @pynvim.command("ScalavistaSetPort", nargs="1")
    def set_port(self, args):
        self.set_server_port(args[0])
        self.check_health()

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
