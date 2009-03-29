"""

This is a Pure Python module to hyphenate text.

It is inspired by Ruby's Text::Hyphen, but currently reads standard *.dic files,
that must be installed separately.

In the future it's maybe nice if dictionaries could be distributed together with
this module, in a slightly prepared form, like in Ruby's Text::Hyphen.

Wilbert Berendsen, March 2008
info@wilbertberendsen.nl

License: LGPL.

"""

import sys
import re
from common import *
#__all__ = ("Hyphenator")

# cache of per-file Hyph_dict objects
hdcache = {}

# precompile some stuff
parse_hex = re.compile(r'\^{2}([0-9a-f]{2})').sub
parse = re.compile(r'(\d?)(\D?)').findall

def hexrepl(matchObj):
    return unichr(int(matchObj.group(1), 16))


class parse_alt(object):
    """
    Parse nonstandard hyphen pattern alternative.
    The instance returns a special int with data about the current position
    in the pattern when called with an odd value.
    """
    def __init__(self, pat, alt):
        alt = alt.split(',')
        self.change = alt[0]
        if len(alt) > 2:
            self.index = int(alt[1])
            self.cut = int(alt[2]) + 1
        else:
            self.index = 1
            self.cut = len(re.sub(r'[\d\.]', '', pat)) + 1
        if pat.startswith('.'):
            self.index += 1

    def __call__(self, val):
        self.index -= 1
        val = int(val)
        if val & 1:
            return dint(val, (self.change, self.index, self.cut))
        else:
            return val


class dint(int):
    """
    Just an int some other data can be stuck to in a data attribute.
    Call with ref=other to use the data from the other dint.
    """
    def __new__(cls, value, data=None, ref=None):
        obj = int.__new__(cls, value)
        if ref and type(ref) == dint:
            obj.data = ref.data
        else:
            obj.data = data
        return obj


class Hyph_dict(object):
    """
    Reads a hyph_*.dic file and stores the hyphenation patterns.
    Parameters:
    -filename : filename of hyph_*.dic to read
    """
    def __init__(self, filename):
        self.patterns = {}
        f = open(filename)
        charset = f.readline().strip()
        if charset.startswith('charset '):
            charset = charset[8:].strip()

        for pat in f:
            pat = pat.decode(charset).strip()
            if not pat or pat[0] == '%': continue
            # replace ^^hh with the real character
            pat = parse_hex(hexrepl, pat)
            # read nonstandard hyphen alternatives
            if '/' in pat:
                pat, alt = pat.split('/', 1)
                factory = parse_alt(pat, alt)
            else:
                factory = int
            tag, value = zip(*[(s, factory(i or "0")) for i, s in parse(pat)])
            # if only zeros, skip this pattern
            if max(value) == 0: continue
            # chop zeros from beginning and end, and store start offset.
            start, end = 0, len(value)
            while not value[start]: start += 1
            while not value[end-1]: end -= 1
            self.patterns[''.join(tag)] = start, value[start:end]
        f.close()
        self.cache = {}
        self.maxlen = max(map(len, self.patterns.keys()))

    def positions(self, word):
        """
        Returns a list of positions where the word can be hyphenated.
        E.g. for the dutch word 'lettergrepen' this method returns
        the list [3, 6, 9].

        Each position is a 'data int' (dint) with a data attribute.
        If the data attribute is not None, it contains a tuple with
        information about nonstandard hyphenation at that point:
        (change, index, cut)

        change: is a string like 'ff=f', that describes how hyphenation
            should take place.
        index: where to substitute the change, counting from the current
            point
        cut: how many characters to remove while substituting the nonstandard
            hyphenation
        """
        word = word.lower()
        points = self.cache.get(word)
        if points is None:
            prepWord = '.%s.' % word
            res = [0] * (len(prepWord) + 1)
            for i in range(len(prepWord) - 1):
                for j in range(i + 1, min(i + self.maxlen, len(prepWord)) + 1):
                    p = self.patterns.get(prepWord[i:j])
                    if p:
                        offset, value = p
                        s = slice(i + offset, i + offset + len(value))
                        res[s] = map(max, value, res[s])

            points = [dint(i - 1, ref=r) for i, r in enumerate(res) if r % 2]
            self.cache[word] = points
        return points


class Hyphenator(SilpaModule):
	"""
	Reads a hyph_*.dic file and stores the hyphenation patterns.
	Provides methods to hyphenate strings in various ways.
	Parameters:
	-filename : filename of hyph_*.dic to read
	-left: make the first syllabe not shorter than this
	-right: make the last syllabe not shorter than this
	-cache: if true (default), use a cached copy of the dic file, if possible

	left and right may also later be changed:
	h = Hyphenator(file)
	h.left = 1
	"""
	#self.left=2
	#def __init__(self, left=2, right=2, cache=True):
	left  = 2
	right = 2

	def loadHyphDict(self,lang, cache=True):
		filename="./modules/hyphenator/rules/hyph_"+lang+".dic"
		if not cache or filename not in hdcache:
			hdcache[filename] = Hyph_dict(filename)
			self.hd = hdcache[filename]
	def positions(self, word):
		"""
		Returns a list of positions where the word can be hyphenated.
		See also Hyph_dict.positions. The points that are too far to
		the left or right are removed.
		"""
		right = len(word) - self.right
		return [i for i in self.hd.positions(word) if self.left <= i <= right]

	def iterate(self, word):
		"""
		Iterate over all hyphenation possibilities, the longest first.
		"""
		if isinstance(word, str):
			word = word.decode('latin1')
		for p in reversed(self.positions(word)):
			if p.data:
				# get the nonstandard hyphenation data
				change, index, cut = p.data
				if word.isupper():
					change = change.upper()
				c1, c2 = change.split('=')
				yield word[:p+index] + c1, c2 + word[p+index+cut:]
			else:
				yield word[:p], word[p:]

	def wrap(self, word, width, hyphen='-'):
		"""
		Return the longest possible first part and the last part of the
		hyphenated word. The first part has the hyphen already attached.
		Returns None, if there is no hyphenation point before width, or
		if the word could not be hyphenated.
		"""
		width -= len(hyphen)
		for w1, w2 in self.iterate(word):
			if len(w1) <= width:
				return w1 + hyphen, w2

	def inserted(self, word, hyphen='-'):
		"""
		Returns the word as a string with all the possible hyphens inserted.
		E.g. for the dutch word 'lettergrepen' this method returns
		the string 'let-ter-gre-pen'. The hyphen string to use can be
		given as the second parameter, that defaults to '-'.
		"""
		if isinstance(word, str):
			word = word.decode('latin1')
		l = list(word)
		for p in reversed(self.positions(word)):
			if p.data:
				# get the nonstandard hyphenation data
				change, index, cut = p.data
				if word.isupper():
					change = change.upper()
				l[p + index : p + index + cut] = change.replace('=', hyphen)
			else:
				l.insert(p, hyphen)
		return ''.join(l)
	def process(self,form):
		response = """
		<h2>Hyphenate Text</h2></hr>
		<p>Enter the text for  hyphenation in the below text area.
		 Language of each  word will be detected. 
		 You can give the text in any language and even with mixed language
		</p>
		<form action="" method="post">
		<textarea cols='100' rows='25' name='input_text' id='id1'>%s</textarea>
		<input  type="submit" id="Hyphenate" value="Hyphenate"  name="action" style="width:12em;"/>
		<input type="reset" value="Clear" style="width:12em;"/>
		</br>
		</form>
		"""
		if(form.has_key('input_text')):
			text = action=form['input_text'].value	.decode('utf-8')
			response=response % text
			words=text.split(" ")
			response = response+"<h2>Language Detection Results</h2></hr>"
			response = response+"<table class=\"table1\"><tr><th>Word</th><th>Hyphenated Word</th></tr>"
			for word in words:
				word=word.strip()
				if(word>""):
					mm=ModuleManager()
					ld = mm.getModuleInstance("Detect Language")
					lang=ld.detect_lang(word)[word]
					self.loadHyphDict(lang)
					hyph_word = self.inserted(word)
					response = response+"<tr><td>"+word+"</td><td>"+hyph_word+"</td></tr>"
			response = response+"</table>	"
		else:
			response=response % ""	
		return response
	def get_module_name(self):
		return "Hyphentator"
	def get_info(self):
		return 	"Hyphenates each word in the text in all possible positions"	
		
def getInstance():
	return Hyphenator()

#    __call__ = iterate


if __name__ == "__main__":

    dict_file = sys.argv[1]
    word = sys.argv[2].decode('latin1')

    h = Hyphenator(dict_file, left=1, right=1)

    for i in h(word):
        print i
