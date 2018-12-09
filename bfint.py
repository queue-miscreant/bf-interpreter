#!/usr/bin/env python3
'''
Badly implemeneted brainfuck interpreter. Terminates when end of program is
reached or when ',' returns EOF

Options:
	-g:			Debug mode. Adds the characters ! and ? to the brainfuck
				instruction set. ! will halt, show memory and program, and await
				a debug command. ? is a softer breakpoint that only turns on after
				a ! has been encountered. ? will be ignored again after the current
				scope (pair of matching []) is exited
	-s [delay]:	Always show memory/instruction strip. Neat for demo'ing code
	-min:		Remove characters not in ',.[]+-<>?!', write program to the same
				filename but with '.min' appended, and exit
'''
import sys
import os
import functools
import time

def pretty_array(array, index, length, pattern):
	# don't think about it too hard. We start `half_width` cells behind, and
	# end when `array` ends, or until we've gone `length` characters
	width_predict = len(pattern % array[0]) + 1
	half_width = length//2 - 1
	start = max(index-half_width, 0)
	ran = max(half_width-index, 0)
	return ' '*(width_predict*ran) + '│'.join([pattern % i for i in \
		array[start:start+length-ran]])

class _Debugger:
	'''
	Internal debugger class. When an instance is called by Interpreter, a value
	with bool == True allows the current instruction to be executed. Otherwise,
	execution is completely halted until continue.
	'''
	def __init__(self, parent):
		self.parent = parent
		self.last_command = 'c'
		self.dispatch = {
			  "next":		parent.dispatch[">"]
			, "previous":	parent.dispatch["<"]
			, "step":		lambda: 1
			, "set":		self.set
			, "continue":	self.cont
		}

	def cont(self):
		self.parent.bp = False

	def set(self, args):
		self.parent.memory[self.parent.dptr] = args[0]

	def __call__(self):
		cmd = input('(bfdb) \x1b[K').split()
		if not cmd:
			cmd = self.last_command

		for i in self.dispatch:
			if i.find(cmd[0]) == 0:
				self.last_command = i
				try:
					return self.dispatch[i](cmd[1:])
				except TypeError:
					return self.dispatch[i]()
		print("\nNot a command: '%s'\x1b[A" % cmd[0], flush=True
			, file=sys.stderr)
		return None

class Interpreter:
	'''
	Interpreter class.

	@param program Minimized brainfuck code
	@param debug Whether or not to allow !? and launch Debugger
	@param always Whether to show the strips after every instruction.
	'''
	MAXINT = 256
	DELAY = 0

	def __init__(self, program, debug, always):
		# internal storage
		self.memory = [0 for i in range(300)] #data stored here
		self.dptr = 0 #where in the data
		self.program = program
		self.iptr = 0 #where in the program
		self.jumps = {}
		self.print_input = True
		# debug information
		self.always = always	# always show the strips
		self.max = 0			# highest cell
		self.bp = False			# breakpoints
		self.bp_soft = False
		# prepare dispatch table
		self.dispatch = {
			  '+':	functools.partial(self.inc, 1)
			, '-':	functools.partial(self.inc, -1)
			, '>':	functools.partial(self.moveptr, 1)
			, '<':	functools.partial(self.moveptr, -1)
			, '[':	self.startbranch
			, ']':	self.endbranch
			, '.':	lambda: self.outfile.write(chr(self.memory[self.dptr]))
			, ',':	self.input
			, '!':	functools.partial(self.breakpoint, True)
			, '?':	functools.partial(self.breakpoint, False)
		}
		# prepare jumps
		jumpstack = []
		for i, j in enumerate(self.program):
			if j == '[':
				jumpstack.append(i)
			elif j == ']':
				jump = jumpstack.pop()
				self.jumps[i] = jump
				self.jumps[jump] = i

		if sys.stderr.isatty() and (always or debug):
			#save cursor position
			print(end="\n\n\n\n\n\x1b[5A\x1b[s\x1b[?25l", file=sys.stderr)

		#line buffered, not system default
		if not debug:
			outfile = os.dup(sys.stdout.fileno())
			self.outfile = os.fdopen(outfile, 'w', 1)
			self.debug = None
			return

		self.debug = _Debugger(self)

	def show_strip(self):
		'''
		Shows the program memory and normal memory in a human-friendly format.
		I've already done the math; this works, it's just really ugly
		'''
		# recall cursor
		print(end="\x1b[u", file=sys.stderr)

		# if ouput is going to be 8 cells in either direction (center is cell 8)
		# 7 * 4 spaces + 2 for centering = column 30
		print((' '*29)+'v', file=sys.stderr)

		print(pretty_array(self.memory, self.dptr, 16, "%3.d"), end="\x1b[K\n"
			, file=sys.stderr)
		print(pretty_array(self.program, self.iptr, 16, " %s "), end="\x1b[K\n"
			, file=sys.stderr)
		#3 lines printed, 4th line for input

	def inc(self, direction):
		self.memory[self.dptr] = (self.memory[self.dptr] + direction) % self.MAXINT

	def moveptr(self, direction):
		self.dptr = (self.dptr + direction) % len(self.memory)
		self.max = max(self.dptr, self.max)

	def startbranch(self):
		if not self.memory[self.dptr]:
			self.iptr = self.jumps[self.iptr]

	def endbranch(self):
		if self.memory[self.dptr]:
			self.iptr = self.jumps[self.iptr]
		#skip consecutive ]s
		else:
			self.bp_soft = False
			for i in range(self.iptr+1, len(self.program)):
				if self.program[i] != ']':
					self.iptr = i-1
					break

	def input(self):
		if sys.stdin.isatty():
			if self.print_input:
				print(end="Input: \x1b[K", file=sys.stderr, flush=True)
			char = sys.stdin.read(1)
			if char == '\n':
				if self.print_input:
					char = ''
				else:
					self.print_input = True
					self.input()
					return
			else:
				self.print_input = False
		else:
			char = sys.stdin.read(1)

		if not char:
			#-1 because after dispatch exit, instruction is incremented
			self.iptr = len(self.program)-1
		else:
			self.memory[self.dptr] = ord(char)

	def breakpoint(self, hard):
		if not self.debug:
			return
		if hard:
			self.bp = True
			self.bp_soft = False
		elif self.bp_soft:
			self.bp = True

	def interpret(self):
		ins = self.program[self.iptr]
		self.dispatch[ins]()

	def start(self):
		if self.debug:
			self.outfile = open("debug.txt", 'a+')
		try:
			while self.iptr < len(self.program):
				if self.bp:					#debugger
					self.show_strip()
					if not self.debug():
						continue
				elif self.always:			#show strips anyway
					self.show_strip()
				ins = self.program[self.iptr]
				self.dispatch[ins]()
				self.iptr += 1
				if not self.bp and self.DELAY:
					time.sleep(self.DELAY)
		except KeyboardInterrupt:
			pass
		if self.always:
			self.show_strip()
		self.outfile.flush()
		if self.debug:
			print("Number of bytes used: %d" % self.max)
			print("Output written to debug.txt")
			self.outfile.close()

def main():
	if len(sys.argv) == 1 or not os.path.isfile(sys.argv[1]):
		return

	program = ""
	with open(sys.argv[1]) as a:
		program = a.read()
	always = "-s" in sys.argv
	isdebug = "-d" in sys.argv
	delay = 0
	if isdebug and not sys.stdin.isatty():
		print("ERROR: Cannot run debug while accepting stdin input")
		return

	if always:
		try:
			delay = float(sys.argv[sys.argv.index("-s") + 1])
		except (IndexError, ValueError):
			pass

#	if not sys.stdin.isatty():
#		stdin_data = sys.stdin.read()
	progmin = [i for i in program if i in '+-<>[]!?.,']
	if "-min" in sys.argv:
		with open(sys.argv[1]+".min", 'w') as a:
			a.write(''.join(progmin))
	else:
		interpret = Interpreter(progmin, isdebug, always)
		interpret.DELAY = delay
		interpret.start()
		print(end="\x1b[?25h", file=sys.stderr)

if __name__ == "__main__":
	main()
