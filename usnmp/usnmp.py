#SNMP versions
SNMP_VER1 = 0x00

#ASN.1 primitives
ASN1_INT = 0x02
ASN1_OCTSTR = 0x04 #OctetString
ASN1_OID = 0x06 #ObjectIdentifier
ASN1_NULL = 0x05
ASN1_SEQ = 0x30 #sequence

#library fudge specific binary octstr
#------------------------------------
#labelling of binary decoded ocstr vals
#as discrete from string decoded is req'd
#to allow unpack/pack to return same result
ASN1_OCTSTR_BIN = 0xff

#SNMP specific SEQUENCE types
SNMP_GETREQUEST = 0xa0
SNMP_GETRESPONSE = 0xa2
SNMP_GETNEXTREQUEST = 0xa1

#SNMP specific integer types
SNMP_COUNTER = 0x41
SNMP_GUAGE = 0x42
SNMP_TIMETICKS = 0x43

#SNMP specific other types
SNMP_IPADDR = 0x40
SNMP_OPAQUE = 0x44 #not implemented
SNMP_NSAPADDR = 0x45 #not implemented

#SNMP error codes
SNMP_ERR_NOERROR = 0x00
SNMP_ERR_TOOBIG = 0x01
SNMP_ERR_NOSUCHNAME = 0x02
SNMP_ERR_BADVALUE = 0x03
SNMP_ERR_READONLY = 0x04
SNMP_ERR_GENERR = 0x05


class SnmpPacket():
    def __init__(self, *args, **kwargs):
        if len(args) == 1:
            self.unpacked = unpack(args[0])
        else:
            self.unpacked = unpack(_SNMP_PACKET_PROTO)
        for arg in kwargs:
            if arg not in ['mib', 'unpacked', 'packed'] \
                    and hasattr(self, arg):
                setattr(self, arg, kwargs[arg])
        self.mib = _SnmpPacketMib(self.unpacked[1][2][1][3][1])
    @property
    def packed(self): return pack(self.unpacked)
    @property
    def ver(self): return self.unpacked[1][0][1]
    @ver.setter
    def ver(self, v): self.unpacked[1][0][1] = v
    @property
    def community(self): return self.unpacked[1][1][1]
    @community.setter
    def community(self, v): self.unpacked[1][1][1] = v
    @property
    def type(self): return self.unpacked[1][2][0]
    @type.setter
    def type(self, v): self.unpacked[1][2][0] = v
    @property
    def id(self): return self.unpacked[1][2][1][0][1]
    @id.setter
    def id(self, v): self.unpacked[1][2][1][0][1] = v
    @property
    def err_status(self): return self.unpacked[1][2][1][1][1]
    @err_status.setter
    def err_status(self, v): self.unpacked[1][2][1][1][1] = v
    @property
    def err_id(self): return self.unpacked[1][2][1][2][1]
    @err_id.setter
    def err_id(self, v): self.unpacked[1][2][1][2][1] = v


class _SnmpPacketMib():
    def __init__(self, mib):
        self.mib = mib
    def __getitem__(self, oid):
        for oid_tv in self.mib:
            if oid_tv[1][0][1] == oid:
                return oid_tv[1][1][0], oid_tv[1][1][1]
        return None
    def __setitem__(self, oid, tv):
        existing = False
        for oid_tv in self.mib:
            if oid_tv[1][0][1] == oid:
                existing = True
                oid_tv[1][1] = tv
                break
        if not existing:
            self.mib.append([ASN1_SEQ, [[ASN1_OID, oid], list(tv)]])
    def __repr__(self):
        s = "{"
        for oid_tv in self.mib:
            if len(s) > 1:
                s += ", "
            s += "'" + oid_tv[1][0][1] + "': (" + \
                 str(oid_tv[1][1][0]) + ", " + str(oid_tv[1][1][1]) + ")"
                #micropython tuple has no __repr__()
                #tuple(oid_tv[1][1]).__repr__()
        return s + "}"
    def __iter__(self):
        for oid_tv in self.mib:
            yield oid_tv[1][0][1]
    def __delitem__(self, oid):
        for i, oid_tv in enumerate(self.mib):
            if oid_tv[1][0][1] == oid:
                del(self.mib[i])

def pack(p):
    t,v = p
    if type(v) is list:
        #deepcopy the list
        v = v[:]
        for i, val in enumerate(v):
            v[i] = pack(val)
    return pack_tlv(t,v)

def pack_tlv(t, v):
    b=bytearray()
    if t in (ASN1_SEQ, \
             SNMP_GETREQUEST, SNMP_GETRESPONSE, SNMP_GETNEXTREQUEST):
        for block in v:
            b.extend(block)
    #octet strings that unpack as python strings
    elif t == ASN1_OCTSTR:
        b = bytearray(map(ord, v))
    #octet strings that unpack as string of hex value pairs
    elif t == ASN1_OCTSTR_BIN:
        ptr = 0
        b = bytearray()
        while ptr<len(v):
            b.append( int(v[ptr:ptr+2], 16) )
            ptr += 2
        t = ASN1_OCTSTR
    elif t in (ASN1_INT, SNMP_COUNTER, SNMP_GUAGE, SNMP_TIMETICKS):
        #can't eecode -ve (do -ve values occur in snmp?)
        if v < 0:
            raise Exception("-ve int")
        else:
            b.append(v & 0xff)
            v //= 0x100
            while v > 0:
                b = bytearray([v & 0xff]) + b
                v //= 0x100
            #+ve values with high 0rder bit set are prefixed by 0x0
            #observed in snmp, indicating -ve snmp ints are possible?
            if b[0]&0x80==0x80:
                b = bytearray([0x0]) + b
    elif t == ASN1_NULL:
        l = 0x0
    elif t == ASN1_OID:
        oid = v.split(".")
        oid = list(map(int, oid))
        #first two indexes are encoded in single byte
        b.append(oid[0]*40 + oid[1])
        for id in oid[2:]:
            if 0 <= id < 0x7f:
                b.append(id)
            #check RFC's for correct upperbound
            elif 0x7f < id < 0x7fff:
                b.append(id//0x80+0x80)
                b.append(id&0x7f)
            else:
                raise ValueError("oid chunk out of bounds")
    elif t == SNMP_IPADDR:
        for byte in map(int, v.split(".")):
            b.append(byte)
    elif t in (SNMP_OPAQUE, SNMP_NSAPADDR):
        raise Exception("SNMP_[OPAQUE & NSAPADDR] not implemented")
    return bytearray([t]) + pack_len(len(b)) + b

def pack_len(l):
    if l < 0x80:
        return bytearray([l])
    else:
        b = bytearray()
        while l>0:
            b = bytearray([l&0xff]) + b
            l //= 0x100
        return bytearray([0x80+len(b)]) + b

def unpack(b):
    t,l,v = unpack_tlv(b)
    if type(v) is list:
        for i, val in enumerate(v):
            v[i] = unpack(val)
    elif type(v) is bytearray:
        v = unpack(v)
    return [t,v]

def unpack_tlv(b):
    ptr = 0
    t = b[ptr]
    l, l_incr = unpack_len(b)
    ptr +=  1 + l_incr
    #sequence types
    if t in (ASN1_SEQ, \
             SNMP_GETREQUEST, SNMP_GETRESPONSE, SNMP_GETNEXTREQUEST):
        v = []
        while ptr < len(b):
            lb, lb_incr = unpack_len( b[ptr:] )
            v.append( b[ptr : ptr+1+lb_incr+lb] )
            ptr += 1 + lb + lb_incr
    #octet string
    elif t == ASN1_OCTSTR:
        #if binary data contains unprintables (e.g. a mac-addr)
        #  decode as a string of hex value pairs
        #  return a non-standard type-code as a hint to pack_tlv
        #else decode as python string
        printable = True
        for byte in b[ptr:ptr+1]:
            if not 128>byte>31:
                printable = False
                break
        #if l == 6 or not printable:
        if not printable:
            t = ASN1_OCTSTR_BIN
            v = ""
            for byte in b[ptr : ptr+l]:
                if byte<0x10:
                    v += '0' + hex(byte)[2:]
                else:
                    v += hex(byte)[2:]
        else:
            v = bytes(b[ptr : ptr+l]).decode()
    elif t in (ASN1_INT, SNMP_COUNTER, SNMP_GUAGE, SNMP_TIMETICKS):
        #can't decode -ve (do -ve values occur in snmp?)
        v=0
        for byte in b[ptr:]:
            v = v*0x100 + byte
    elif t == ASN1_NULL:
        if b[1]==0 and len(b)==2:
            v=None
        else:
            raise Exception("bad null encoding")
    elif t == ASN1_OID:
        #first 2 indexes are encoded in single byte
        v = str( b[ptr]//0x28 ) + "." + str( b[ptr]%0x28 )
        ptr += 1
        high_septet = 0
        for byte in b[ptr:]:
            if byte&0x80 == 0x80:
                high_septet = byte - 0x80
            else:
                v += "." + str(high_septet*0x80 + byte)
                high_septet = 0
    elif t == SNMP_IPADDR:
        v = str(b[ptr])
        for byte in b[ptr+1:]:
            v += "." + str(byte)
    elif t in (SNMP_OPAQUE, SNMP_NSAPADDR):
        raise Exception("SNMP_[OPAQUE & NSAPADDR] not implemented")
    else:
        raise Exception("invalid type", t)
    return t, 1+l+l_incr, v

def unpack_len(v):
    if v[1]&0x80 == 0x80:
        l = 0
        for i in v[2 : 2+v[1]&0x7f]:
            l = l*0x100 + i
        return l, 1 + v[1]&0x7f
    else:
        return v[1], 1

def hex2str(v):
    ptr = 0
    s = ""
    while ptr<len(v):
        s += chr( int(v[ptr:ptr+2], 16) )
        ptr += 2
    return s

#template packet
_SNMP_PACKET_PROTO = pack_tlv(ASN1_SEQ,[
    pack_tlv(ASN1_INT, SNMP_VER1),
    pack_tlv(ASN1_OCTSTR, ""),
    pack_tlv(SNMP_GETREQUEST,[
        pack_tlv(ASN1_INT,1),
        pack_tlv(ASN1_INT,0),
        pack_tlv(ASN1_INT,0),
        pack_tlv(ASN1_SEQ,[])
    ])
])