"""Focused level placement regressions; run python -B -m unittest test_levels.py."""
import math
import struct
import unittest
from types import SimpleNamespace
import levels
import cooked

class PlacementTests(unittest.TestCase):
    def test_nonuniform_instance_transform(self):
        m=levels.matrix([0,0,-1],[1,0,0],[10,20,30],[2,3,4])
        self.assertEqual(m,[0,0,-2,0,0,3,0,0,4,0,0,0,10,20,30,1])

    def test_packed_header_fields(self):
        h=bytearray(116);h[1]=1
        for off,values in [(2,(1,0,0)),(14,(0,0,1)),(26,(10,20,30)),(38,(2,3,4))]:struct.pack_into('<3f',h,off,*values)
        struct.pack_into('<III',h,50,257,123,456);h[62:67]=b'Tree\0';struct.pack_into('<III',h,94,789,12,34)
        child=b'GINH'+struct.pack('<I',120)+h
        b=b'GINS'+struct.pack('<I',len(child)+4)+child
        result=levels.instances(SimpleNamespace(b=b,records=[('GINS',0,len(b))]))[0]
        self.assertEqual(result['geometryHash'],789);self.assertEqual(result['parentHash'],12)
        self.assertEqual(result['matrix'][12:15],[10,20,30]);self.assertEqual(result['flags'],257)
        self.assertEqual(result['name'],'Tree')

    def test_sky_does_not_expand_playable_bounds(self):
        for name in ['STATIC_Starscape','STATIC_MoonAGlow','INST_HorizonNebula1']:self.assertEqual(levels.layer(name),'Skybox')

class RenderingTests(unittest.TestCase):
    def packet(self,bits,components,attribute):
        xyz=[(0,0,0),(0x3f800000,0,0),(0,0x3f800000,0)]
        return cooked.Scene.packet(None,[
            dict(address=0,values=[(0,0,0,0)]*2),
            dict(address=4,bits=32,components=3,values=xyz),
            dict(address=2,components=2,values=[(0,0),(4096,0),(0,4097)]),
            dict(address=3,bits=bits,components=components,values=[attribute]*3)],[],[])

    def test_ps2_vertex_color_unity_and_alpha(self):
        for bits in (5,8):
            mesh=self.packet(bits,4,(128,64,32,128))
            self.assertEqual(mesh['colors'],[[1,.5,.25]]*3)
            self.assertEqual(mesh['alphas'],[1]*3)
            self.assertTrue(mesh['bakedLighting'])
        self.assertEqual(self.packet(8,4,(128,128,128,64))['alphas'],[.5]*3)

    def test_adc_bit_does_not_shift_uv(self):
        mesh=self.packet(8,4,(128,128,128,128))
        self.assertEqual(mesh['uvs'][-1],[0,1])
        self.assertEqual(mesh['indices'],[0,1,2])

    def test_lit_prop_keeps_authored_normals(self):
        mesh=self.packet(16,3,(0,32767,0))
        self.assertAlmostEqual(mesh['normals'][0][1],1,places=4)
        self.assertNotIn('bakedLighting',mesh)

    def test_saved_ambient_and_directional_light(self):
        records=[];b=bytearray()
        for kind in (0,1):
            h=bytearray(72);h[0]=1;h[1]=kind
            struct.pack_into('<I',h,2,65535);h[6:9]=bytes([255,128,0])
            struct.pack_into('<f',h,10,.25);struct.pack_into('<I',h,26,kind+10)
            child=b'LITH'+struct.pack('<I',76)+h
            record=b'LITB'+struct.pack('<I',len(child)+4)+child
            records.append(('LITB',len(b),len(record)));b.extend(record)
            h=bytearray(116);h[1]=1
            struct.pack_into('<3f',h,14,0,0,1);struct.pack_into('<I',h,50,1);struct.pack_into('<I',h,94,kind+10)
            child=b'LINH'+struct.pack('<I',120)+h
            record=b'LINS'+struct.pack('<I',len(child)+4)+child
            records.append(('LINS',len(b),len(record)));b.extend(record)
        lights=levels.lights(SimpleNamespace(b=b,records=records))
        self.assertEqual(len(lights),2)
        self.assertEqual(lights[0]['color'],[.5,128/510,0])
        self.assertEqual(lights[1]['direction'],[0,0,-1])

if __name__=='__main__':unittest.main()
