#!/usr/bin/env python3

import os, re, sys, signal
from random import randint

PLACE_AT_MOUSE = int(
    os.getenv('TEXT_PLACE_AT_MOUSE', '0'))
FONT_SIZE_OFFSET = int(
    os.getenv('TEXT_FONT_SIZE_OFFSET', '10'))
WRAP_MODE = \
    os.getenv('TEXT_WRAP_MODE', 'word')
SCROLLBAR_MODE = int(
    os.getenv('TEXT_SCROLLBAR_MODE', '1'))
SCROLLBAR_AUTOHIDE = int(
    os.getenv('TEXT_SCROLLBAR_AUTOHIDE', '1'))
ISEARCH_CASE_INSENSITIVE = int(
    os.getenv('TEXT_ISEARCH_CASE_INSENSITIVE', '1'))
FONT_NAME = \
    os.getenv('TEXT_FONT_NAME', 'TkFixedFont')
WIDTH = int(os.getenv('WIDTH', '80'))
HEIGHT = int(os.getenv('HEIGHT', '15'))

sys.stdout.close()
#sys.stderr.close()

(pipe_r, pipe_w) = os.pipe()
if os.fork():  # are we the father?
    # we only act as a data-passer:  read from stdin and write to the pipe.
    os.close(pipe_r)
    while True:  # until eof is found: copy stdin to stdout
        try:
            s = os.read(sys.stdin.fileno(), 64 << 10)
        except KeyboardInterrupt:
            sys.exit(130)
        if not s:
            sys.exit(0)
        os.write(pipe_w, s)


# the rest is for the child:

sys.stdin.close()
os.close(pipe_w)

signal.signal(signal.SIGINT, signal.SIG_IGN)  # ignore sigint

# import tkinter only in the child:

from tkinter import font
import tkinter

tk = tkinter.Tk()

# choose a slightly random background color:
def get_random_color(r=(0x90, 0xd0), g=(0xe0, 0xff), b=(0x90, 0xe0)):
    return '#%02x%02x%02x' % (randint(r[0], r[1]),
                              randint(g[0], g[1]),
                              randint(b[0], b[1]))

color = get_random_color()

# some default values
place_at_mouse = bool(PLACE_AT_MOUSE)
scrollbar_switch_default = SCROLLBAR_MODE
scrollbar_auto_hide_default = SCROLLBAR_AUTOHIDE
wrap_mode_value = WRAP_MODE

# command line parsing:
while len(sys.argv) > 1 and sys.argv[1].startswith('-'):
    if   sys.argv[1] == '-m':  # place at mouse
        place_at_mouse = True
        sys.argv.pop(1)
    elif sys.argv[1] == '-s':  # scrollbars
        scrollbar_switch_default = 1
        sys.argv.pop(1)
    elif sys.argv[1] == '-h':  # auto hide for scrollbars
        scrollbar_auto_hide_default = 1
        sys.argv.pop(1)
    elif sys.argv[1] == '-w':  # wrap mode
        sys.argv.pop(1)
        wrap_mode_value = sys.argv.pop(1)
    elif sys.argv[1] == '-g':  # geometry
        sys.argv.pop(1)
        tk.geometry(sys.argv.pop(1))
    else:  # unknown option
        raise Exception("Unknown option: %r" % sys.argv[1])

if place_at_mouse:
    x, y = tk.winfo_pointerxy()
    x = max(0, x-20)
    y = max(0, y-20)
    tk.wm_geometry('+%d+%d' % (x, y))

tk.configure(background=color)

font = font.nametofont(FONT_NAME)

wrap_mode = tkinter.StringVar(tk)
wrap_mode.set(wrap_mode_value)
fontSize = tkinter.IntVar(tk)
fontSize.set(abs(font.config()['size']) + FONT_SIZE_OFFSET)

_vs = tkinter.Scrollbar(tk, background=color, trough=color)
_hs = tkinter.Scrollbar(tk, background=color, trough=color)

def set_vs(start, end):
    global _vs
    if (not scrollbars_switch.get() or
        (scrollbars_auto_hide.get() and start == '0' and end == '1')):
        _vs.config(width=0, borderwidth=0)
    else:
        _vs.config(width=10, borderwidth=2)
    _vs.set(start, end)

def set_hs(start, end):
    global _hs
    if (not scrollbars_switch.get() or
        (scrollbars_auto_hide.get() and start == '0' and end == '1')):
        _hs.config(width=0, borderwidth=0)
    else:
        _hs.config(width=10, borderwidth=2)
    _hs.set(start, end)

def quit(*args, **kwargs):
    sys.exit(0)

_vs.bind('q', quit)
_hs.bind('q', quit)

_vs.focus()

_t = tkinter.Text(tk, width=WIDTH, height=HEIGHT,
          yscrollcommand=set_vs,
          xscrollcommand=set_hs,
          font=font, wrap=wrap_mode.get(), setgrid=1,
          background=color,
          borderwidth=0)
_t.mark_set('stdin', 'insert')
_vs.config(orient='vert', command=(_t, 'yview'))
_hs.config(orient='hori', command=(_t, 'xview'))
_t.grid(row=0, column=0, sticky='nsew')
_vs.grid(row=0, column=1, sticky='ns')
_hs.grid(row=1, column=0, sticky='ew')
tk.columnconfigure(0, weight=1)
tk.rowconfigure(0, weight=1)

_t_m = tkinter.Menu(tk, tearoff=0)

def set_wrap_mode():
    global wrap_mode, _t
    _t.config(wrap=wrap_mode.get())

scrollbars_switch = tkinter.IntVar(tk)
scrollbars_switch.set(scrollbar_switch_default)
_t_m.add_checkbutton(variable=scrollbars_switch,
                     label='scrollbars',
                     onvalue=1, offvalue=0)
scrollbars_auto_hide = tkinter.IntVar(tk)
scrollbars_auto_hide.set(scrollbar_auto_hide_default)
_t_m.add_checkbutton(variable=scrollbars_auto_hide,
                     label='scrollbars automatic hide',
                     onvalue=1, offvalue=0)
_t_m.add_separator()
_t_m.add_radiobutton(variable=wrap_mode, value='char', label='wrap char',
                     command=set_wrap_mode)
_t_m.add_radiobutton(variable=wrap_mode, value='word', label='wrap word',
                     command=set_wrap_mode)
_t_m.add_radiobutton(variable=wrap_mode, value='none', label='wrap none',
                     command=set_wrap_mode)
_t_m.add_separator()
isearch_case_insensitive = tkinter.IntVar(tk)
isearch_case_insensitive.set(ISEARCH_CASE_INSENSITIVE)
_t_m.add_checkbutton(variable=isearch_case_insensitive,
                     label='isearch case insensitive',
                     onvalue=1, offvalue=0)
isearch_regexp = tkinter.IntVar(tk)
isearch_regexp.set(0)
_t_m.add_checkbutton(variable=isearch_regexp,
                     label='isearch regexp',
                     onvalue=1, offvalue=0)

def shift_button_event(event):
    global _t_m
    _t_m.tk_popup(event.x_root, event.y_root)
    return 'break'

_t.bind('<Shift-Button>', shift_button_event)

def f10_event(event):
    color = get_random_color()
    tk.configure(background=color)
    _t.config(background=color)
    _vs.config(background=color, trough=color)
    _hs.config(background=color, trough=color)

_t.bind('<F10>', f10_event)

def increase_font(event, amount=1):
    fontSize.set(min(30, fontSize.get() + amount))
    font.config(size=fontSize.get())
    return 'break'

def decrease_font(event, amount=1):
    fontSize.set(max(1, fontSize.get() - amount))
    font.config(size=fontSize.get())
    return 'break'
decrease_font(None, 2)

def fit(event):
    text = _t.get('1.0', 'end')
    lines = text.split('\n')
    while lines[-1] == '': lines.pop()
    height = min(len(lines), 100)
    width = min(max(len(line) for line in lines), 400)
    _t.configure(width=width+2, height=height+1)
    return 'break'

for widget in (_t, tk):
    widget.bind('<Control-plus>', increase_font)
    widget.bind('<Control-minus>', decrease_font)
    widget.bind('<Control-q>', quit)
    widget.bind('<Control-m>', fit)

_i = tkinter.Frame(tk)
isearch_string = tkinter.StringVar(tk)
_i_string = tkinter.Label(textvariable=isearch_string)
_i_string.pack(in_=_i, side='left', fill='x')
isearch_bad_regexp = tkinter.StringVar(tk)
_i_bad_regexp = tkinter.Label(textvariable=isearch_bad_regexp)
_i_bad_regexp.pack(in_=_i, side='left', fill='x')
isearch_direction = tkinter.StringVar(tk)
isearch_direction.set('-forwards')

def start_isearch(direction):
    global isearch_direction, isearch_string, _i, _t
    _i.grid(row=2, columnspan=2)
    isearch_direction.set(direction)
    isearch_string.set('')
    _t.unbind('<Control-s>')
    _t.unbind('<Control-r>')
    _t.bind('<Any-Key>', lambda e: isearch_mode_key(e))

old_isearch_string = ''

def end_isearch():
    global old_isearch_string, isearch_string
    _i.grid_forget()
    if isearch_string.get() != '':
        old_isearch_string = isearch_string.get()
    _t.unbind('<Any-Key>')
    _t.bind('<Control-s>', lambda e: start_isearch('-forwards'))
    _t.bind('<Control-r>', lambda e: start_isearch('-backwards'))

def isearch_mode_key(event):
    global isearch_string, isearch_direction, old_isearch_string
    if event.char:
        if   ord(event.char) in range(32, 255):  # printable?
            isearch_string.set(isearch_string.get() + event.char)
        elif event.char in '\x13\x12':  # C-s, C-r
            if event.char == '\x13':  # C-s
                isearch_direction.set('-forwards')
            else:
                isearch_direction.set('-backwards')
            if isearch_string.get() == '':
                # no isearch_string yet?  use the old one:
                isearch_string.set(old_isearch_string)
            else:
                # incremental search
                if isearch_direction.get() == '-forwards':
                    _t.mark_set('insert', 'insert +1 chars')
                else:
                    _t.mark_set('insert', 'insert -1 chars')
        elif event.char == '\b':  # backspace
            if len(isearch_string.get()) == 0:
                tk.bell()
            else:
                isearch_string.set(isearch_string.get()[:-1])
        elif event.char in '\x1b\n\r':  # esc
            end_isearch()
        else:
            pass  # print('unparsed char: %r' % (event.char,))
    elif event.keysym in [ 'Left', 'Right', 'Up', 'Down', 'Return',
                           'Escape', 'Insert', 'Delete', 'End', 'Home',
                           'Prior', 'Next',
                           'KP_Home', 'KP_Up', 'KP_Prior', 'KP_Left',
                           'KP_Begin', 'KP_Right', 'KP_End', 'KP_Down',
                           'KP_Next', 'KP_Insert', 'KP_Delete', 'KP_Enter',
                           'F1', 'F2', 'F3', 'F4', 'F5', 'F6', 'F7', 'F8',
                           'F9', 'F10', 'F11', 'F12', 'Print', 'Pause' ]:
        end_isearch()
    else:
        pass  # print('unparsed keysym: %r' % (event.keysym,))
    if isearch_string.get() != '':
        try:
            found = _t.search(pattern=isearch_string.get(),
                              index='insert',
                              backwards=(isearch_direction.get() ==
                                         '-backwards'),
                              regexp=isearch_regexp.get(),
                              nocase=isearch_case_insensitive.get())
        except TclError:
            isearch_bad_regexp.set('regexp not parsable')
        else:
            isearch_bad_regexp.set('')
            if found == '':  # nothing found?
                tk.bell()
            else:
                # check for wrap around:
                if (isearch_direction.get() == '-forwards' and
                    _t.compare('insert', '>', found) or
                    isearch_direction.get() == '-backwards' and
                    _t.compare('insert', '<', found)):
                    tk.bell()
                _t.mark_set('insert', found)
                _t.see(found)
    return 'break'

_t.bind('<Control-s>', lambda e: start_isearch('-forwards'))
_t.bind('<Control-r>', lambda e: start_isearch('-backwards'))

old_s = None  # None is mark for: not an esc char before this one
current_foreground = None
current_background = None
tag_counter = 0

def drain_pipe(a, b):

    def set_foreground(colour):
        global current_foreground
        current_foreground = colour

    def set_background(colour):
        global current_background
        current_background = colour

    def invert():
        global current_background, current_foreground
        if current_background is None:
            if current_foreground is None:
                current_background = "black"
                current_foreground = "lightgrey"
            else:  # foreground is set, default background
                current_background = current_foreground
                current_foreground = "lightgrey"
        else:  # background is set
            if current_foreground is None:
                current_background = "black"
                current_foreground = current_background
            else:  # both are set
                current_background, current_foreground = \
                                    current_foreground, current_background

    def insert(s):
        'receives a string without ESC sequences;'\
        ' sets proper tags in the text widget for colours and then inserts'\
        ' the string;'\
        ' does not return anything'

        def insert_raw(s, tag=None):
            'receives a string without ESC sequences;'\
            ' assumes that the text widget is already tagged properly for'\
            ' colours and inserts the string;'\
            ' does not return anything'

            def insert_one_line(s, tag):
                if s:
                    # remove all text from input position to line end:
                    _t.delete('stdin', 'stdin lineend')
                    # insert the given text (with the optional tag):
                    try:
                        s = s.decode('utf-8')
                    except ValueError:
                        pass  # ignore utf-8 decoding problems
                              # use raw string then
                    if tag:  _t.insert('stdin', s, tag)
                    else:    _t.insert('stdin', s)

            while True:  # for each unfinished line (terminated by CR alone)
                i = s.find(b'\r')
                if i < 0:
                    break
                insert_one_line(s[:i], tag)
                s = s[i+1:]  # strip off inserted part
                _t.mark_set('stdin', "stdin linestart")
            insert_one_line(s, tag)

        global current_foreground, current_background, tag_counter
        if current_foreground or current_background:
            tag = '%d' % tag_counter
            insert_raw(s, tag)
            if current_foreground:
                _t.tag_config(tag, foreground=current_foreground)
            if current_background:
                _t.tag_config(tag, background=current_background)
            tag_counter += 1
        else:
            insert_raw(s)

    def process_substring(s, is_last):
        'receives a string without ESCs; the string is following an ESC;'\
        ' returns the rest to be stored in old_s (maybe None, empty or an'\
        ' unfinished part of an ESC sequence)'

        def parse_colour(number, background=False):
            if   number == b'0':  # black
                return 'black'
            elif number == b'1':  # red
                return '#f88' if background else 'red'
            elif number == b'2':  # green
                return '#8f8' if background else '#080'
            elif number == b'3':  # yellow
                return '#ff8' if background else '#880'
            elif number == b'4':  # blue
                return '#88f' if background else 'blue'
            elif number == b'5':  # purple
                return '#f8f' if background else 'purple'
            elif number == b'6':  # cyan
                return '#8ff' if background else '#088'
            elif number == b'7':  # white
                return 'white'
            else:
                print('Warning: colour not parsed:', number,
                      file=sys.stderr)
                return None  # *shrug*

        # match the beginning of the string for legal esc sequences:
        m = re.match(br'^\[(?P<args>([^;a-zA-Z]+;)*[^;a-zA-Z]*)'
                     br'(?P<cmd>[a-zA-Z])', s)
        if m:  # match found
            s = s[m.span()[1]:]  # strip the matched part
            if m.groupdict()['cmd'] == b'm':
                args = m.groupdict()['args'].split(b';')
                for arg in args:
                    if   arg in (b'', b'0', b'00'):  # norm
                        set_foreground(None)
                        set_background(None)
                    elif arg[0:1] == b'3':  # foreground
                        if len(arg) > 1:
                            set_foreground(parse_colour(arg[1:2]))
                        else:
                            set_foreground(None)
                    elif arg[0:1] == b'4':  # background
                        if len(arg) > 1:
                            set_background(parse_colour(
                                arg[1:2], background=True))
                        else:
                            set_background(None)
                    elif arg[0:1] == b'7':  # invert
                        invert()
                    else:
                        pass  # print('arg to m not parsed:', arg)
            elif m.groupdict()['cmd'] == b'J':  # clear?
                _t.delete('0.0', 'end')
            else:
                pass  # print('sequence not parsed:', m.groupdict())
        else:  # no match found, no legal escape sequence
            if is_last:
                if len(s) < 10:  # maybe incomplete?  (cheap heuristic)
                    return s
                else:  # no, not incomplete, just no match
                    insert(s)
                    return None
        insert(s)
        return b''

    global old_s
    s = os.read(pipe_r, 100000)
    s = s.replace(b'\x0f', b'')  # remove all SIs
    s = re.sub(b'.\b', b'', s)  # remove all backspaces
    if s:
        if old_s is not None:
            s = old_s + s
        # find out whether we are scrolled to the end of the text:
        at_end = (_t.yview()[1] == 1.0)
        ss = s.split(b'\x1b')
        for s in ss[:-1]:  # now work all parts following an esc char
            if old_s is None:  # not following esc char?
                insert(s)
                old_s = b''
            else:
                old_s = process_substring(s, is_last=0)
        if len(ss) > 1:
            old_s = process_substring(ss[-1], is_last=1)
        else:
            insert(s)
            old_s = None
        # scroll to the end again if we have been there:
        if at_end:
            _t.yview_moveto(1)
    else:
        # nothing more to read: deregister this handler
        tk.deletefilehandler(pipe_r)
        if old_s is not None:
            insert(old_s)  # flush the last few chars
        os.close(pipe_r)

tk.createfilehandler(pipe_r, tkinter.READABLE, drain_pipe)

tk.mainloop()
