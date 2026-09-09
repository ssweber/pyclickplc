"""Hardware facts from the CLICK 3.92 module catalog.

Model IDs: SystemConfig.dll's module table (also SC_ModuleInformation.ini
for expansions). Discrete counts: SC_ModuleInformation.ini Data1/Data2;
analog counts: its channel lists and CPU descriptions. Recorded 2026-09-08.
IDs 41 (C0-08TD1-1) and 244 (C0-02DA-D) have model names in the DLL but no
INI entry and no published product page or manual listing; their counts are
inferred from the sibling models C0-08TD1 and C0-02DR-D.
Reading a project does not require CLICK installed. No vendor descriptions
or executable code are included here.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Module:
    """Installed module identity and physical I/O counts.

    A count of zero means the module has no I/O of that kind. Counts
    describe hardware capacity, not currently assigned channel addresses.
    """

    module_id: int
    model: str
    discrete_inputs: int
    discrete_outputs: int
    analog_inputs: int
    analog_outputs: int


_MODULE_CATALOG = {
    225: Module(225, "C0-00DD1-D", 8, 6, 0, 0),
    226: Module(226, "C0-00DD2-D", 8, 6, 0, 0),
    227: Module(227, "C0-00DR-D", 8, 6, 0, 0),
    228: Module(228, "C0-00DA-D", 8, 6, 0, 0),
    229: Module(229, "C0-00AA-D", 8, 6, 0, 0),
    230: Module(230, "C0-00AR-D", 8, 6, 0, 0),
    233: Module(233, "C0-01DD1-D", 8, 6, 0, 0),
    234: Module(234, "C0-01DD2-D", 8, 6, 0, 0),
    235: Module(235, "C0-01DR-D", 8, 6, 0, 0),
    236: Module(236, "C0-01DA-D", 8, 6, 0, 0),
    237: Module(237, "C0-01AA-D", 8, 6, 0, 0),
    238: Module(238, "C0-01AR-D", 8, 6, 0, 0),
    241: Module(241, "C0-02DD1-D", 4, 4, 2, 2),
    242: Module(242, "C0-02DD2-D", 4, 4, 2, 2),
    243: Module(243, "C0-02DR-D", 4, 4, 2, 2),
    244: Module(244, "C0-02DA-D", 4, 4, 2, 2),
    208: Module(208, "C0-10DD1E-D", 8, 6, 0, 0),
    209: Module(209, "C0-10DD2E-D", 8, 6, 0, 0),
    210: Module(210, "C0-10DRE-D", 8, 6, 0, 0),
    211: Module(211, "C0-10ARE-D", 8, 6, 0, 0),
    212: Module(212, "C0-11DD1E-D", 8, 6, 0, 0),
    213: Module(213, "C0-11DD2E-D", 8, 6, 0, 0),
    214: Module(214, "C0-11DRE-D", 8, 6, 0, 0),
    215: Module(215, "C0-11ARE-D", 8, 6, 0, 0),
    216: Module(216, "C0-12DD1E-D", 4, 4, 2, 2),
    217: Module(217, "C0-12DD2E-D", 4, 4, 2, 2),
    218: Module(218, "C0-12DRE-D", 4, 4, 2, 2),
    219: Module(219, "C0-12ARE-D", 4, 4, 2, 2),
    220: Module(220, "C0-12DD1E-1-D", 4, 4, 4, 2),
    221: Module(221, "C0-12DD2E-1-D", 4, 4, 4, 2),
    222: Module(222, "C0-12DRE-1-D", 4, 4, 4, 2),
    223: Module(223, "C0-12ARE-1-D", 4, 4, 4, 2),
    192: Module(192, "C0-12DD1E-2-D", 4, 4, 4, 2),
    193: Module(193, "C0-12DD2E-2-D", 4, 4, 4, 2),
    194: Module(194, "C0-12DRE-2-D", 4, 4, 4, 2),
    195: Module(195, "C0-12ARE-2-D", 4, 4, 4, 2),
    196: Module(196, "C2-01CPU", 0, 0, 0, 0),
    197: Module(197, "C2-02CPU", 0, 0, 0, 0),
    198: Module(198, "C2-03CPU", 0, 0, 0, 0),
    199: Module(199, "C2-01CPU-2", 0, 0, 0, 0),
    200: Module(200, "C2-02CPU-2", 0, 0, 0, 0),
    201: Module(201, "C2-03CPU-2", 0, 0, 0, 0),
    8: Module(8, "C0-08ND3", 8, 0, 0, 0),
    9: Module(9, "C0-08ND3-1", 8, 0, 0, 0),
    10: Module(10, "C0-08NA", 8, 0, 0, 0),
    11: Module(11, "C0-08NE3", 8, 0, 0, 0),
    12: Module(12, "C0-08SIM", 8, 0, 0, 0),
    16: Module(16, "C0-16ND3", 16, 0, 0, 0),
    19: Module(19, "C0-16NE3", 16, 0, 0, 0),
    37: Module(37, "C0-04TRS", 0, 4, 0, 0),
    38: Module(38, "C0-04TRS-10", 0, 4, 0, 0),
    40: Module(40, "C0-08TD1", 0, 8, 0, 0),
    41: Module(41, "C0-08TD1-1", 0, 8, 0, 0),
    42: Module(42, "C0-08TD2", 0, 8, 0, 0),
    44: Module(44, "C0-08TA", 0, 8, 0, 0),
    45: Module(45, "C0-08TR", 0, 8, 0, 0),
    46: Module(46, "C0-08TR-3", 0, 8, 0, 0),
    48: Module(48, "C0-16TD1", 0, 16, 0, 0),
    50: Module(50, "C0-16TD2", 0, 16, 0, 0),
    66: Module(66, "C0-08CDR", 4, 4, 0, 0),
    72: Module(72, "C0-16CDD1", 8, 8, 0, 0),
    73: Module(73, "C0-16CDD2", 8, 8, 0, 0),
    256: Module(256, "C0-00AC", 0, 0, 0, 0),
    512: Module(512, "C0-01AC", 0, 0, 0, 0),
    160: Module(160, "C0-04AD", 0, 0, 4, 0),
    161: Module(161, "C0-04AD-1", 0, 0, 4, 0),
    162: Module(162, "C0-04AD-2", 0, 0, 4, 0),
    163: Module(163, "C0-04DA-1", 0, 0, 0, 4),
    164: Module(164, "C0-04DA-2", 0, 0, 0, 4),
    165: Module(165, "C0-4AD2DA-1", 0, 0, 4, 2),
    166: Module(166, "C0-4AD2DA-2", 0, 0, 4, 2),
    167: Module(167, "C0-04THM", 0, 0, 4, 0),
    168: Module(168, "C0-04RTD", 0, 0, 4, 0),
    177: Module(177, "C0-04POT", 0, 0, 4, 0),
    169: Module(169, "C0-08AD-1", 0, 0, 8, 0),
    170: Module(170, "C0-08AD-2", 0, 0, 8, 0),
    171: Module(171, "C0-08DA-1", 0, 0, 0, 8),
    172: Module(172, "C0-08DA-2", 0, 0, 0, 8),
    173: Module(173, "C0-16ADH-1", 0, 0, 16, 0),
    174: Module(174, "C0-16ADH-2", 0, 0, 16, 0),
    175: Module(175, "C0-16DAH-1", 0, 0, 0, 16),
    176: Module(176, "C0-16DAH-2", 0, 0, 0, 16),
    8193: Module(8193, "C2-14D1", 8, 6, 0, 0),
    8194: Module(8194, "C2-14D2", 8, 6, 0, 0),
    8195: Module(8195, "C2-14DR", 8, 6, 0, 0),
    8196: Module(8196, "C2-14AR", 8, 6, 0, 0),
    8197: Module(8197, "C2-14TTL", 8, 6, 0, 0),
    8208: Module(8208, "C2-08D1-4VC", 4, 4, 2, 2),
    8209: Module(8209, "C2-08D2-4VC", 4, 4, 2, 2),
    8210: Module(8210, "C2-08DR-4VC", 4, 4, 2, 2),
    8211: Module(8211, "C2-08AR-4VC", 4, 4, 2, 2),
    8212: Module(8212, "C2-08D1-6C", 4, 4, 4, 2),
    8213: Module(8213, "C2-08D2-6C", 4, 4, 4, 2),
    8214: Module(8214, "C2-08DR-6C", 4, 4, 4, 2),
    8215: Module(8215, "C2-08AR-6C", 4, 4, 4, 2),
    8216: Module(8216, "C2-08D1-6V", 4, 4, 4, 2),
    8217: Module(8217, "C2-08D2-6V", 4, 4, 4, 2),
    8218: Module(8218, "C2-08DR-6V", 4, 4, 4, 2),
    8219: Module(8219, "C2-08AR-6V", 4, 4, 4, 2),
    8224: Module(8224, "C2-DCM", 0, 0, 0, 0),
    8225: Module(8225, "C2-NRED", 0, 0, 0, 0),
    8226: Module(8226, "C2-OPCUA", 0, 0, 0, 0),
}
