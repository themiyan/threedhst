"""
3DHST.shifts

Utilities for computing shifts and processing shiftfiles.
"""

__version__ = "$Rev$"
# $URL$
# $Author$
# $Date$

import os
import pyfits
import pyraf
from pyraf import iraf
from iraf import stsdas,dither

import threedhst
import threedhst.prep_flt_files

no = iraf.no
yes = iraf.yes
INDEF = iraf.INDEF

def run_tweakshifts(asn_direct, verbose=False, clean=True):
    """
run_tweakshifts(asn_direct)
    
    asn_direct - filename of ASN table of direct images [...]_asn.fits
    
    This routine only uses dither.tweakshifts to compute the relative shifts of 
    the direct images
    """
    
    root = asn_direct.split('_asn.fits')[0]#.lower()

    try:
        os.remove(root+'_tweak.fits')
    except:
        pass        

    iraf.flpr()
    iraf.flpr()
    iraf.flpr()
    if clean:
        clean=iraf.yes
    else:
        clean=iraf.no
        
    status = iraf.tweakshifts(input=asn_direct, shiftfile='',
                     reference=root+'_tweak.fits',
                     output = root+'_shifts.txt', findmode = 'catalog',
                     gencatalog = 'daofind', sextractpars = '', 
                     undistort = yes, computesig = yes, idckey = 'idctab', \
       clean = clean, verbose = no, catfile = '', xcol = 1, ycol = 2, \
       fluxcol = 3, fluxmax = INDEF, fluxmin = INDEF, fluxunits = 'counts', \
       nbright = INDEF, refcat = '', refxcol = 1, refycol = 2, rfluxcol = 3, \
       rfluxmax = INDEF, rfluxmin = INDEF, rfluxunits = 'counts', \
       refnbright = INDEF, minobj = 15, nmatch = 30, matching = 'tolerance', \
       xyxin = INDEF, xyyin = INDEF, tolerance = 4.0, fwhmpsf = 1.5, \
       sigma = 0.0, datamin = INDEF, datamax = INDEF, threshold = 4.0, \
       nsigma = 1.5, fitgeometry = 'rxyscale', function = 'polynomial', \
       maxiter = 3, reject = 3.0, crossref = '', margin = 50, tapersz = 50, \
       pad = no, fwhm = 7.0, ellip = 0.05, pa = 45.0, fitbox = 7, \
    Stdout=1)
    
    if verbose:
        for line in status:
            print line
    
    return status
    
def find_align_images_that_overlap(DIRECT_MOSAIC, ALIGN_IMAGE, ALIGN_EXTENSION=0, is_region=False):
    """
align_img_list = find_align_images_that_overlap()
    
    Look through the images defined in threedhst.options['ALIGN_IMAGE'] and 
    return a list of only those that overlap.  
    
    This was written for the GOODS fields, where the multiple GOODS ACS tiles
    can be used to align the F140W images.  ALIGN_IMAGE will be something like 
    h_nz_sect*, but you don't want to waste time swarping large images that 
    don't overlap with the target image.
    """
    import glob
    import numpy as np
    import threedhst.regions
    #ROOT_DIRECT = threedhst.options['ROOT_DIRECT']
    align_images = glob.glob(ALIGN_IMAGE)
    
    #### Get polygon of the direct mosaic edges
    px, py = threedhst.regions.wcs_polygon(DIRECT_MOSAIC, extension=1)
    
    #### Loop through align_images and check if they overlap with the 
    #### direct mosaic
    align_img_list = []
    for align_image in align_images:
        if is_region:
            #### Read a polygon defined in a region file
            lines = open(align_image).readlines()
            for line in lines:
                if line.startswith('polygon'):
                    spl = line.split('(')[1].split(')')[0].split(',')
                    qx = np.cast[float](spl[::2])
                    qy = np.cast[float](spl[1::2])
                    break
            align_image = align_image.replace('pointing.reg','fits')
        else:
            qx, qy = threedhst.regions.wcs_polygon(align_image,
                extension=ALIGN_EXTENSION)
                
        if threedhst.regions.polygons_intersect(px, py, qx, qy):
            align_img_list.append(align_image)
    
    return align_img_list

def refine_shifts(ROOT_DIRECT='f160w',
                  ALIGN_IMAGE='../../ACS/h_sz*drz_img.fits',
                  fitgeometry='shift', clean=True,
                  ALIGN_EXTENSION=0):
    """
refine_shifts(ROOT_DIRECT='f160w',
              ALIGN_IMAGE='../../ACS/h_sz*drz_img.fits',
              fitgeometry='shift', clean=True)
                
    Refine shifts by catalog matching an input multidrizzle image, 
    ROOT_DIRECT+'_drz.fits' to one or more alignment images
    """
    import numpy as np
    
    threedhst.showMessage('Aligning WCS to %s (%s)'
              %(threedhst.options['ALIGN_IMAGE'], fitgeometry))
    
    run = threedhst.prep_flt_files.MultidrizzleRun(ROOT_DIRECT.upper())
    
    ## radius for match is 2**toler.  Make it larger if fit comes out bad
    toler, maxtoler = 3, 5  
    xrms, yrms = 100, 100
    while ((xrms > 1) | (yrms > 1)) & (toler <= maxtoler):
        xshift, yshift, rot, scale, xrms, yrms = threedhst.shifts.align_to_reference(
                        ROOT_DIRECT,
                        ALIGN_IMAGE,
                        fitgeometry=fitgeometry, clean=clean,
                        ALIGN_EXTENSION=ALIGN_EXTENSION,
                        toler=toler, skip_swarp=(toler > 3))
        toler+=1

    #### shifts measured in DRZ frame.  Translate to FLT frame
    drz = pyfits.open(ROOT_DIRECT+'_drz.fits')
    #alpha = (180.-drz[1].header['PA_APER'])/360.*2*np.pi
    #### Get reference angle from first image in the ASN file
    asn = threedhst.utils.ASNFile(ROOT_DIRECT+'_asn.fits')
    alpha = (180.-pyfits.getheader(asn.exposures[0]+'_flt.fits',1)['PA_APER'])/360.*2*np.pi
    
    xsh = (xshift*np.cos(alpha)-yshift*np.sin(alpha))*np.float(run.scl)
    ysh = (xshift*np.sin(alpha)+yshift*np.cos(alpha))*np.float(run.scl)

    print 'Final shift:', xsh, ysh, drz[1].header['PA_APER']
    fp = open(ROOT_DIRECT+'_align.info','w')
    fp.write('%s %8.3f %8.3f %8.3f\n' %(ALIGN_IMAGE, xsh, ysh, rot)) 
    fp.close()
    
    #### Read the shiftfile
    shiftF = threedhst.shifts.ShiftFile(ROOT_DIRECT+'_shifts.txt')
            
    #### Apply the alignment shifts to the shiftfile
    shiftF.xshift = list(np.array(shiftF.xshift)-xsh)
    shiftF.yshift = list(np.array(shiftF.yshift)-ysh)
    shiftF.rotate = list((np.array(shiftF.rotate)+rot) % 360)
    shiftF.scale = list(np.array(shiftF.scale)*scale)
    
    shiftF.write(ROOT_DIRECT+'_shifts.txt')
    
def align_to_reference(ROOT_DIRECT, ALIGN_IMAGE, fitgeometry="shift",
    clean=True, verbose=False, ALIGN_EXTENSION=0, toler=3, skip_swarp=False):
    """
xshift, yshift, rot, scale, xrms, yrms = align_to_reference()
    """        
    import os
    import glob
    import shutil
    import numpy as np
    
    #### Clean slate    
    rmfiles = ['SCI.fits','WHT.fits','align.cat','direct.cat'
               'align.map','align.match','align.reg','align.xy', 
               'direct.reg','direct.xy']
    
    for file in rmfiles:
        try:
            os.remove(file)
        except:
            pass
                
    #### Get only images that overlap from the ALIGN_IMAGE list    
    align_img_list = find_align_images_that_overlap(ROOT_DIRECT+'_drz.fits',
                                                    ALIGN_IMAGE,
                                     ALIGN_EXTENSION=ALIGN_EXTENSION)
    if not align_img_list:
        print 'threedhst.shifts.align_to_reference: no alignment images overlap.'
        return 0,0
    
    #### Use swarp to combine the alignment images to the same image 
    #### dimensions as the direct mosaic
    if not skip_swarp:
        try:
            os.remove(ROOT_DIRECT+'_align.fits')
        except:
            pass
        matchImagePixels(input=align_img_list,
                     matchImage=ROOT_DIRECT+'_drz.fits',
                     output=ROOT_DIRECT+'_align.fits', match_extension = 1,
                     input_extension=ALIGN_EXTENSION)
                     
    #### Run SExtractor on the direct image, with the WHT 
    #### extension as a weight image
    se = threedhst.sex.SExtractor()
    se.aXeParams()
    se.copyConvFile()
    se.overwrite = True
    se.options['CHECKIMAGE_TYPE'] = 'NONE'
    se.options['WEIGHT_TYPE']     = 'MAP_WEIGHT'
    se.options['WEIGHT_IMAGE']    = 'WHT.fits'
    se.options['FILTER']    = 'Y'
    ## Detect thresholds (default = 1.5)
    se.options['DETECT_THRESH']    = '10' 
    se.options['ANALYSIS_THRESH']  = '10' 
    se.options['MAG_ZEROPOINT'] = str(threedhst.options['MAG_ZEROPOINT'])

    #### Run SExtractor on direct and alignment images
    ## direct image
    se.options['CATALOG_NAME']    = 'direct.cat'
    iraf.imcopy(ROOT_DIRECT+'_drz.fits[1]',"SCI.fits")
    iraf.imcopy(ROOT_DIRECT+'_drz.fits[2]',"WHT.fits")
    status = se.sextractImage('SCI.fits')

    ## alignment image
    se.options['CATALOG_NAME']    = 'align.cat'
    status = se.sextractImage(ROOT_DIRECT+'_align.fits')

    ## Read the catalogs
    directCat = threedhst.sex.mySexCat('direct.cat')
    alignCat = threedhst.sex.mySexCat('align.cat')
        
    xshift = 0
    yshift = 0
    rot = 0
    scale = 1.
    
    NITER = 5
    IT = 0
    while (IT < NITER):
        IT = IT+1
        
        #### Get x,y coordinates of detected objects
        ## direct image
        fp = open('direct.xy','w')
        for i in range(len(directCat.X_IMAGE)):
            fp.write('%s  %s\n' %(directCat.X_IMAGE[i],directCat.Y_IMAGE[i]))
        fp.close()

        ## alignment image
        fp = open('align.xy','w')
        for i in range(len(alignCat.X_IMAGE)):
            fp.write('%s  %s\n' %(np.float(alignCat.X_IMAGE[i])+xshift,
                       np.float(alignCat.Y_IMAGE[i])+yshift))
        fp.close()

        iraf.flpr()
        iraf.flpr()
        iraf.flpr()
        #### iraf.xyxymatch to find matches between the two catalogs
        pow = toler*1.
        try:
            os.remove('align.match')
        except:
            pass
        status1 = iraf.xyxymatch(input="direct.xy", reference="align.xy",
                       output="align.match",
                       tolerance=2**pow, separation=0, verbose=yes, Stdout=1)
        
        while status1[-1].startswith('0'):
            pow+=1
            os.remove('align.match')
            status1 = iraf.xyxymatch(input="direct.xy", reference="align.xy",
                           output="align.match",
                           tolerance=2**pow, separation=0, verbose=yes, Stdout=1)
            
        if verbose:
            for line in status1:
                print line
                
        #### Compute shifts with iraf.geomap
        iraf.flpr()
        iraf.flpr()
        iraf.flpr()
        try:
            os.remove("align.map")
        except:
            pass
            
        status2 = iraf.geomap(input="align.match", database="align.map",
                    fitgeometry=fitgeometry, interactive=no, 
                    xmin=INDEF, xmax=INDEF, ymin=INDEF, ymax=INDEF,
                    maxiter = 10, reject = 2.0, Stdout=1)
        if verbose:
            for line in status2:
                print line
        
        #fp = open(root+'.iraf.log','a')
        #fp.writelines(status1)
        #fp.writelines(status2)
        #fp.close()
        
        xshift, yshift, rot, scale, xrms, yrms = 0,0,0,1,2,2
        
        #### Parse geomap.output 
        fp = open("align.map","r")
        for line in fp.readlines():
            spl = line.split()
            if spl[0].startswith('xshift'):
                xshift += float(spl[1])    
            if spl[0].startswith('yshift'):
                yshift += float(spl[1])    
            if spl[0].startswith('xrotation'):
                rot = float(spl[1])    
            if spl[0].startswith('xmag'):
                scale = float(spl[1])    
            if spl[0].startswith('xrms'):
                xrms = float(spl[1])    
            if spl[0].startswith('yrms'):
                yrms = float(spl[1])    
            
        fp.close()
        
        #os.system('wc align.match')
        print 'Shift iteration #%d, xshift=%f, yshift=%f, rot=%f, scl=%f (rms: %5.2f,%5.2f)' %(IT, xshift, yshift, rot, scale, xrms, yrms)
    
    im = pyfits.open('SCI.fits')
        
    shutil.copy('align.map',ROOT_DIRECT+'_align.map')
    
    #### Cleanup
    if clean:
        rmfiles = ['SCI.fits','WHT.fits','align.cat',
               'align.map','align.match','align.reg','align.xy',
               'direct.cat','direct.reg','direct.xy',
               'drz_sci.fits','drz_wht.fits','bg.fits']
        
        for file in rmfiles:
            try:
                os.remove(file)
            except:
                pass
        
    return xshift, yshift, rot, scale, xrms, yrms
    
def matchImagePixels(input=None,matchImage=None,output=None,
                     input_extension=0, match_extension=0):
    """
matchImagePixels(input=None,matchImage=None,output=None,
                 match_extension=0)
    
    SWarp input image to same size/scale as matchIMage.
    Output default is input_root+'.match.fits'
    
    """
    from threedhst.sex import SWarp
    
    #input = '/research/HST/GRISM/WEINER/ACS/h_nz_sect33_v2.0_drz_img.fits'
    #matchImage = 'IB3721050_SCI.fits'
    
    if not input:
        return False
    
    if not output:
        output = os.path.basename(input).split('.fits')[0]+'.match.fits'
    
    #### initialize SWarp
    sw = SWarp()
    sw._aXeDefaults()
    sw.overwrite = True
    
    #### Get first guess coordinates
    sw.swarpMatchImage(matchImage,extension=match_extension)
    status = sw.swarpImage(matchImage+'[%d]' %match_extension,mode='wait')
    os.remove('coadd.fits')
    os.remove('coadd.weight.fits')
    
    #### Recenter
    sw.swarpRecenter()
    
    #### Make the final output image
    sw.options['IMAGEOUT_NAME'] = output
    #sw.options['WEIGHTOUT_NAME'] = base+'.match.weight.fits'
    
    for i,im in enumerate(input):
        input[i] += '[%d]' %input_extension
    status = sw.swarpImage(input,mode='direct')
    os.remove('coadd.weight.fits')

def make_blank_shiftfile(asn_file='ib3721050_asn.fits',
    xshift=0, yshift=0, rot=0., scale=1.0):
    """
make_blank_shiftfile(asn_file='ib3721050_asn.fits',
        xshift=0, yshift=0, rot=0., scale=1.0)
    
    Make a shiftfile with empty shifts and rotations for all exposures defined
    in an ASN file.
    """
    import threedhst
    
    asn = threedhst.utils.ASNFile(asn_file)
    root = asn_file.split('_asn.fits')[0]
    out = root+'_shifts.txt'
    
    fp = open(out,'w')
    fp.write("""# frame: output
# refimage: %s_flt.fits[1]
# form: delta 
# units: pixels\n""" %(asn.exposures[0]))
    
    for exp in asn.exposures:
        fp.write("%s_flt.fits %10.4f %10.4f %10.4f %10.4f\n" %(exp, xshift, yshift, rot, scale))
    
    fp.close()
    
def make_grism_shiftfile(asn_direct, asn_grism):
    """
make_grism_shiftfile(asn_direct, grism_direct)
    
    Make a shiftfile for grism exposures to match
    corresponding direct images
    """
    from threedhst.utils import ASNFile
    ROOT_DIRECT = asn_direct.split('_asn.fits')[0]#.lower()
    ROOT_GRISM  =  asn_grism.split('_asn.fits')[0]#.lower()
    #### Read shiftfile and ASN table
    sf = ShiftFile(ROOT_DIRECT+'_shifts.txt')
    asn = ASNFile(asn_grism)
    
    if sf.nrows == len(asn.exposures):
        #### Assume one direct image for each grism images, so just
        #### change the image names in the shiftfile to the grism exposures
        for i,exp in enumerate(asn.exposures):
            sf.images[i] = exp+'_flt.fits'
    else:
        #### Have different number of grism and direct images.  Just use the 
        #### shifts/rotations for the first direct image
        xs = sf.xshift[0]
        ys = sf.yshift[0]
        rot = sf.rotate[0]
        scl = sf.scale[0]
        sf.images = []
        sf.xshift = []
        sf.yshift = []
        sf.rotate = []
        sf.scale = []
        for i,exp in enumerate(asn.exposures):
            sf.images.append(exp+'_flt.fits')
            sf.xshift.append(xs)
            sf.yshift.append(ys)
            sf.rotate.append(rot)
            sf.scale.append(scl)
        
        sf.nrows = len(asn.exposures)
        
    #### Write the new shiftfile
    sf.write(ROOT_GRISM+'_shifts.txt')
    
    #print "\n3DHST.shifts.make_grism_shiftfile: %s_shifts.txt\n" %ROOT_GRISM
    threedhst.showMessage('Making grism shiftfile, %s_shifts.txt' %ROOT_GRISM)
    

def checkShiftfile(asn_direct):
    """
checkShiftfile(asn_direct)
    
    Make sure that there is a line in the shiftfile for each exposure 
    in the ASN table.
    """
    from threedhst.utils import ASNFile
    asn = ASNFile(asn_direct)
    
    sf_file = asn_direct.split('_asn.fits')[0]+'_shifts.txt'
    sf = ShiftFile(sf_file)
    flag=False
    for exp in asn.exposures:
        if exp+'_flt.fits' not in sf.images:
            flag=True
            print 'Exposure, %s, not in %s' %(exp,sf_file)
            #print sf.nrows
            sf.append(exp+'_flt.fits')
            #print sf.nrows
            
    if flag:
        sf.write(sf_file)
    else:       
        #print "\n3DHST.shifts.checkShiftfile: %s looks OK.\n" %sf_file
        threedhst.showMessage('Shiftfile, %s, looks OK' %sf_file)
    
class ShiftFile():
    """
ShiftFile(infile)
    
    Read and manipulate a shiftfile produced by, e.g., tweakshifts
    
    Based on aXe2html.sextractcat
    """
    def __init__(self, filename):
        linelist = self.opencat(filename)
        self.headerlines = self.extractheader(linelist)
        rowlines    = self.extractrows(linelist)
        self.processrows(rowlines)
        self.nrows = len(rowlines)
    
    def opencat(self, filename):
        """
        Input:
            filename - the name of the sextractor ascii catalog
            
        Return:
                linelist - a list wit all lines of the sextractor
                       catalog
                       
        Description:
            Opens the file and stores all the lines in a list.

        """
        listfile = open(filename,'r')
        linelist = listfile.readlines()
        return linelist
    
    
    def extractheader(self, linelist):
        """
    Input:
        linelist - all lines of a sextractor catalog

    Return:
        headerlines - the lines which contain header
                      information

    Description:
        Extracts the header lines from the list of lines
        Header lines have a '#' as the first digits and are
        longer than two characters. This allows for small
        cosmetical changes to the original Sextractor tables
        """
        headerlines = []
        for index in range(len(linelist)):
            oneline = linelist[index]
            if (oneline[0] == "#") and (len(oneline)) > 2:
                headerlines.append(oneline)
        return headerlines
    
    def extractrows(self, linelist):
        """
    Input:
        linelist - all lines of a sextractor catalog
        
    Return:
        rowlines - the content lines of a sextractor
                   catalog

    Description:
        Extracts the content lines from the list of lines.
        Content lines have a all lines except the ones which start with a 
        '#' and are longer than one character. This allows for
        e.g. whitespaces as the last 'rows', which often remain 
        after editing an ascii-file
        
        """
        rowlines = []
        for index in range(len(linelist)):
            oneline = linelist[index]
            if oneline[0] != "#" and len(oneline) > 1:
                rowlines.append(oneline)        
        return rowlines
    
    
    def processrows(self, rowlines):
        """
        processrows(self, rowlines)
        
        Read: image xshift yshift rotate scale from shiftfile.
            
        """
        nlines = len(rowlines)
        self.images = []
        self.xshift = []
        self.yshift = []
        self.rotate = []
        self.scale = []
        for i in range(nlines):
            line = rowlines[i].split()
            self.images.append(line[0])
            self.xshift.append(float(line[1]))
            self.yshift.append(float(line[2]))
            if len(line) > 3:
                self.rotate.append(float(line[3]))
            else:
                self.rotate.append(0.)
                self.scale.append(1.0)
            if len(line) > 4:
                self.scale.append(float(line[4]))
    
    
    def write(self, outfile):
        """write(outfile)"""
        fp = open(outfile,'w')
        fp.writelines(self.headerlines)
        for i in range(self.nrows):
            line = '%-20s %8.4f %8.4f %8.3f %8.3f\n' %(self.images[i],
                self.xshift[i], self.yshift[i], self.rotate[i], self.scale[i])
            fp.write(line)
        fp.close()
    
    def pop(self,idx):
        """
pop(self,idx)
        """
        out = self.images.pop(idx) 
        out = self.xshift.pop(idx) 
        out = self.yshift.pop(idx) 
        out = self.rotate.pop(idx) 
        out = self.scale.pop(idx) 
        self.nrows -= 1
    
    def append(self,image, xshift=0., yshift=0.,
                    rotate=0.0, scale=1.0):
        """
append(self,image, xshift=0., yxhift=0.,
                   rotate=0.0, scale=1.0)
        """
        self.images.extend([image])
        self.xshift.extend([xshift])
        self.yshift.extend([yshift])
        self.rotate.extend([rotate])
        self.scale.extend([scale])
        self.nrows += 1