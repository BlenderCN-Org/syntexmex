#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
Created on Sun Jan  5 13:39:03 2020

@author: Thomas Meschede a.k.a. yeus (yeusblender@gmail.com)

This texture synthesis algorithm takes inspiration from three papers and
combines their papers into a new algorithm:

- Image Quilting for Texture Synthesis and Transfer [Efros, Freeman]
    - taking the optimal-patch seam strategy and
- Fast Texture Synthesis using Tree-structured Vector Quantization [Wei, Levoy]
    - iterations, non-causal buildup local neighbourhood search
- Real-Time Texture Synthesis by Patch-Based Sampling [Liang et al.]
    - building a gaussian image pyramid combined with KD-Trees for
      fast searches

and some more inspiration
- wfc synthesis algorithm

optionally in the future:
- Graphcut Textures: Image and Video Synthesis Using Graph Cuts [Kwatra, Schödl]
-

"""

import random #TODO: introduce seed value
import numpy as np
import skimage
import skimage.io
import skimage.transform
#import gc
import math
import functools
sign = functools.partial(math.copysign, 1) # either of these
import logging
logger = logging.getLogger(__name__)
import tex_synthesize as ts
import pickle


#def norm(x): return np.sqrt(x.dot(x))
def norm(x): return np.sqrt((x*x).sum(-1))
#need to be transposed for correct ultiplcation along axis 1
def normalized(x): return (x.T /norm(x)).T

def calc_angle_vec(u, v):
    """
    >>> u = vec((1.0,1.0,0.0))
    >>> v = vec((1.0,0.0,0.0))
    >>> calc_angle_vec(u,v)*rad
    45.00000000000001
    >>> u = vec((1.0,0.0,0.0))
    >>> v = vec((-1.0,0.0,0.0))
    >>> calc_angle_vec(u,v)*rad
    180.0
    >>> u = vec([-9.38963669e-01, 3.44016319e-01, 1.38777878e-17])
    >>> v = vec([-0.93896367, 0.34401632, 0.])
    >>> u @ v / (norm(v)*norm(u))
    1.0000000000000002
    >>> calc_angle_vec(u,v)*rad
    0.0
    """
    #angle = np.arctan2(norm(np.cross(u,v)), np.dot(u,v))
    res = np.sum(u*v) / (norm(u) * norm(v))
    t = np.clip(res,-1.0,1.0)
    angle = np.arccos(t)
    return angle

def tqdm(iterator, *args, **kwargs):
    return iterator

GB = 1.0/1024**3 #GB factor

@ts.timing
def synthesize_textures_on_uvs(synth_tex=False,
                               seamless_UVs=False,
                               msg_queue=None,
                               edge_iterations=0,
                               *argv, **kwargs):
    """
    msg_queue lets the algorithm share intermediate steps
    when using threaded calculations (queue.Queue)
    """
    target = kwargs['target']
    example = kwargs['example']
    patch_ratio = kwargs['patch_ratio']
    libsize = kwargs['libsize']
    island_uvs = kwargs['island_uvs']
    edge_infos = kwargs['edge_infos']
    if msg_queue is None: msg_queue=False
    
    #TODO: check whether we have "left or right" sided coordinate system

    if synth_tex: #generate initial textures
        #TODO: make sure all islands are taken into account
        logger.info("synthesize uv islands")
        res = target.shape[:2]
        island_uvs_px = np.array([uv[...,::-1] * res[:2] for uv in island_uvs])
        #get a boundingbox for the entire island
        ymin,xmin = island_uvs_px.min(axis = (0,1)).astype(int)-(1,1)
        ymax,xmax = island_uvs_px.max(axis = (0,1)).astype(int)+(1,1)
        #add .5 so that uv coordinates refer to the middle of a pixel
        island_uvs_px = island_uvs_px + (-0.5,-0.5) 
        
        #import ipdb; ipdb.set_trace() # BREAKPOINT
        #target[ymin:ymax,xmin:xmax,0]=0.5
        island_mask = np.zeros(target.shape[:2])
        for uvs in island_uvs_px:
            island_mask[skimage.draw.polygon(*uvs.T)]=1.0
        island_mask = island_mask[ymin:ymax,xmin:xmax]>0
        #target = 
        ts.fill_area_with_texture(target, example,
                                  patch_ratio=patch_ratio, libsize = libsize,
                                  bounding_box=(ymin,xmin,ymax,xmax),
                                  mask = island_mask)
        if msg_queue: msg_queue.put(target)
        #fill mask
        
        #target1,f1,f2,cospxs, bmask = ts.fill_area_with_texture(target, example, verts)
        
        """
        for uvs in [get_face_uvs(bm.faces[fidx]) for fidx in islands[0]]:
        #for island in islands: #render texture for each island
        #for uvs in list(get_uvs(bm).values())[:]:
            #import ipdb; ipdb.set_trace() # BREAKPOINT
            verts = uvs[...,::-1] * res[:2] #transform to pixel space
            mask = 
            #levelset, (miny, minx, maxy, maxx) = ts.get_poly_levelset(verts)
            #target[miny:maxy,minx:maxx,0]=np.ones(w,h)
            mask = levelset>0.0
            target[miny:maxy,minx:maxx,:3][mask]=np.random.rand(3)*0.5+0.5
            # import ipdb; ipdb.set_trace() # BREAKPOINT
            #verts = np.flip(verts,1)
            target1,f1,f2,cospxs, bmask = ts.fill_area_with_texture(target, example, verts)"""

    if seamless_UVs:
        tree_info = None
        for i,(e1,e2) in enumerate(edge_infos):
            logger.info(f"making edge seamless: #{i}")
            #TODO: add pre-calculated island mask to better find "valid" uv pixels
            target, tree_info = ts.make_seamless_edge(e1, e2, target, example,
                                           patch_ratio, libsize, 
                                           tree_info=tree_info,
                                           debug_level=0)
            if msg_queue: msg_queue.put(target)
            if (edge_iterations != 0) and (i >= edge_iterations): break 
        #debug_image(target2)
        #import ipdb; ipdb.set_trace() # BREAKPOINT
        
    return target

def check_face_orientation(face):
    edge_vecs = np.roll(face,1,0)-face
    return np.cross(np.roll(edge_vecs,1,0),edge_vecs)
    
if __name__=="__main__":
    logging.basicConfig(level=logging.INFO)
    logger.setLevel(logging.INFO)
    logging.getLogger('tex_synthesize').setLevel(logging.INFO)

    #logging.get
    
    with open('uv_test_island.pickle', 'rb') as handle:
            uv_info = pickle.load(handle)
            
    #skimage.io.imshow_collection([uv_info["target"],uv_info["example"]])
    
    target = synthesize_textures_on_uvs(synth_tex=True,
                                        seamless_UVs=True,
                                        edge_iterations=0,
                                        **uv_info)
    skimage.io.imshow_collection([target])
    #uv_info['edge_infos'][0]

    #faces = uv_info['island_uvs']
    
    #[check_face_orientation(f) for f in faces]
    