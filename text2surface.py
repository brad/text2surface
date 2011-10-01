#!/usr/bin/python
# -*- coding: utf-8 -*-
from argparse import ArgumentParser
import cairo
import gtk
import os
import pango
import pangocairo
import subprocess

def get_args():
	parser = ArgumentParser(description='Convert text to a surface for OpenSCAD and a .stl if desired.')
	parser.add_argument('-l', dest='list', action='store_const', const=True, default=False, help='List available font families and exit.')
	parser.add_argument('-n', dest='disableAA', action='store_const', const=True, default=False, help='Disable anti-aliasing. This will cause the script to extrude squares instead of using a .dat')
	parser.add_argument('-r', dest='removebase', action='store_const', const=True, default=False, help='Remove base layer from surface. Only applies if exporting to .scad and/or .stl.')
	parser.add_argument('-t', dest='text', type=str, default='RepRap', help='The text to convert')
	parser.add_argument('-f', dest='fontname', type=str, default='Sans', help='The font family to use, to see a list of available fonts use "-l"')
	parser.add_argument('-s', dest='fontstyle', type=str, default='', help='The font style to use. Can be either "italic" or "bold"')
	parser.add_argument('-i', dest='fontsize', type=int, default=70, help='The font size to use')
	parser.add_argument('-d', dest='maxdim', type=int, default=150, help='The maximum size in mm to make the x or y dimension. Only applies if exporting to .scad and/or .stl.')
	parser.add_argument('-z', dest='zheight', type=int, default=5, help='The max z-height of the text, defaults to 5')
	parser.add_argument('-o', dest='filename', type=str, default='text2surface.dat', help='By default, this script just outputs textsurface.dat, which can be imported into an OpenSCAD document. If you specify a .scad filename for this parameter, the script will also output a .scad file which imports the surface. If you specify a .stl filename, the script will go further and generate a .stl file.')
	return parser.parse_args()

def print_fonts():
	font_map = pangocairo.cairo_font_map_get_default()
	print repr([f.get_name() for f in font_map.list_families()])

def get_text_data(fontname, fontstyle, fontsize, text):
	# Create the text layout
	pango_context = gtk.Window().create_pango_context()
	layout = pango.Layout(pango_context)
	font = pango.FontDescription()
	font.set_family(fontname)
	if fontstyle == 'italic':
		font.set_style(pango.STYLE_ITALIC)
	elif fontstyle == 'bold':
		font.set_style(pango.STYLE_OBLIQUE)
	font.set_size(pango.SCALE*fontsize)
	layout.set_font_description(font)
	layout.set_text(text)

	# Create the cairo context
	# BUG, this can be a little too small sometimes so add width
	width = layout.get_pixel_size()[0]+int(args.fontsize/3.5)
	height = layout.get_pixel_size()[1]
	surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
	context = cairo.Context(surf)
	pangocairo_context = pangocairo.CairoContext(context)
	pangocairo_context.set_antialias(cairo.ANTIALIAS_SUBPIXEL)

	#draw a background rectangle:
	context.rectangle(0,0,width,height)
	context.set_source_rgb(1, 1, 1)
	context.fill()

	# Render
	context.set_source_rgb(0, 0, 0)
	pangocairo_context.update_layout(layout)
	pangocairo_context.show_layout(layout)

	# Get the RGBA pixel data
	return [list(surf.get_data()), width, height]

def create_dat(data, zheight, filename, text, disableAA):
	# Convert RGBA data to heights
	rgba = 4
	white = 255*rgba
	textbuffer = ''
	line = []
	lines = []
	i=0
	while i < len(data):
		if i%(width*rgba) == 0 and i != 0:
			line.reverse()
			lines.append(line)
			line = []
		pixel = 0
		for j in range(i, i+rgba):
			pixel += ord(data[i])
		line.append(pixel)
		i += rgba

	# To data
	data = []
	for line in lines:
		textbuffer += '\n'
		row = []
		for pixel in line:
			ratio = 1-float(pixel)/white
			if disableAA:
				row.append(round(ratio))
			else:
				# Numbers (with decimal places) must be reversed so
				# that when the entire textbuffer is reversed later,
				# numbers will be correct
				textbuffer += (' '+repr(ratio*zheight))[::-1]
		if disableAA:
			data.append(row)

	if not disableAA:
		# Reverse the text buffer and write that to the file
		datfilename = filename if filename[-4:] == '.dat' else 'temp_text2surface.dat'
		f = open(datfilename, 'w')
		f.write(textbuffer[::-1])
		f.close()
		print 'Text surface for "'+text+'" is in '+datfilename
	return datfilename if not disableAA else data

def create_scad(data, filename, removebase, width, height, maxdim, disableAA, z):
	if width > height:
		scale = [float(maxdim)/width, (maxdim*float(height)/width)/height, 1]
	else:
		scale = [(maxdim*float(width)/height)/width, float(maxdim)/height, 1]
	scadfilename = filename if filename[-5:] == '.scad' else 'temp_text2surface.scad'
	f = open(scadfilename, 'w')
	if not disableAA:
		if removebase:
			f.write('translate([0, 0, -1]) difference() {\n\t')
		f.write('scale('+repr(scale)+') translate([0, 0, 1]) surface("'+data+'", center=true, convexity=5);')
		if removebase:
			f.write('\n\ttranslate([-0.01, 0, 0]) cube(['+repr(scale[0]*width+0.02)+', '+repr(scale[1]*height)+', 2.01], center=true);\n}')
	else:
		f.write('linear_extrude(height='+repr(z)+') scale('+repr(scale[0:2])+') {\n')
		for y,row in enumerate(data):
			for x,pixel in enumerate(row):
				if pixel == 1:
					f.write('\ttranslate(['+repr(x)+', '+repr(y)+']) square(1);\n')
		f.write('}')
	f.close()
	print 'SCAD file is '+scadfilename
	return scadfilename

def create_stl(filename, scadfilename):
	openscadexec = 'openscad'
	windows = 'C:\Program Files\OpenSCAD\openscad.exe'
	mac = '/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD'
	if os.path.exists(windows):
		openscadexec = windows
	elif os.path.exists(mac):
		openscadexec = mac
	stlfilename = filename
	command = [openscadexec, '-m', 'make', '-s', filename, scadfilename]
	print 'Exporting to STL'
	subprocess.call(command)
	print 'STL file is '+stlfilename

if __name__ == '__main__':
	args = get_args()

	# print font families if that was requested and exit
	if args.list:
		print_fonts()
		exit()

	# Generates an RGBA array, given text and font information
	[data, width, height] = get_text_data(args.fontname, args.fontstyle, args.fontsize, args.text)

	# Outputs a .dat file that OpenSCAD can use with the surface command
	data = create_dat(data, args.zheight, args.filename, args.text, args.disableAA)

	# Generate .scad and/or .stl
	if args.filename[-5:] == '.scad' or args.filename[-4:] == '.stl':
		# Outputs a .scad file that can be used to create a .stl file
		scadfilename = create_scad(data, args.filename, args.removebase, width, height, args.maxdim, args.disableAA, args.zheight)
		if args.filename[-4:] == '.stl':
			# Outputs a printable .stl file
			create_stl(args.filename, scadfilename)
