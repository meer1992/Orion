import struct
import numpy as np
import scipy as sp
from ctypes import *

"""
iwlnl_struct.py
   This class has methods that extracts CSI information from NETLINK data. Can also parse
   data from file, stored using log_to_file.c tool.
   It has the following methods that compress and quantize the V matrix according to the
   802.11n-draft standard.

   @compress - given a unitary matrix V (3x3 for now) it compresses the matrix using
   the procedure described in section 20.3.12.2.3 of 802.11n draft.

   @quantize - given an angle, produced by the @compress method above, the number
   of bits used to quantize and which angle it is (phi or psi) it quantizes the
   angles as described on section 7.3.1.29 of 802.11n draft.

   @concatinate_bits - the resulted, k values, from @quantize method are concatinated
   into a bitstring, result is a single value that is applied on the card.

   @break_bits - is the oposite of @concatinate_bits, given a bitpattern, and number
   of bits used to quantize each angle, it reproduced the k-values.


Astrit Zhushi (c) 2011 a.zhushi@cs.ucl.ac.uk

"""


class iwlnl_struct:
    def __init__(self, raw_data=False, from_file=False):
        if raw_data:
            self.parse(raw_data, from_file)


            # """ Given raw bytes parse it to meaningful CSI information :D
            #
            # @raw_data   - raw bytes (either from NETLINK socket or FILE)
            # @from_file  - speself.y if data was read from NETLINK or FILE, NETLINK default
            # """

    def parse(self, raw_data, from_file=False):
        if not from_file:
            self.unpacked = raw_data[38:]  # skip NETLINK header stuff
        else:
            self.unpacked = raw_data[1:]  # skip the first byte

            # exract noise a b c, bfee_count each held on an unsigned char
            # 0 - 4
            tmp = struct.unpack("BBBBB", self.unpacked[:5])
            self.noise_a = tmp[0]  # 0
            self.noise_b = tmp[1]  # 1
            self.noise_c = tmp[2]  # 2
            self.bfee_count = tmp[3] + (tmp[4] << 8)  # 3
            # extract Nrx, Ntx, rssi_a up to antenna_sel
            # 7 - 19
            tmp = struct.unpack("BBBBBbBBBBBB", self.unpacked[7:19])

            self.Nrx = tmp[0]  # 7
            self.Ntx = tmp[1]  # 8
            self.rssi_a = tmp[2]  # 9
            self.rssi_b = tmp[3]  # 10
            self.rssi_c = tmp[4]  # 11
            self.noise = tmp[5]  # 12
            self.agc = tmp[6]  # 13
            self.antenna_sel = tmp[7]  # 14
            self.length = tmp[8] + (tmp[9] << 8)  # 15-16
            self.rate = tmp[10] + (tmp[11] << 8)  # 16-17
            # number of subcarriers
            self.nrs = 30
            self.perm = []
            self.perm.append(((self.antenna_sel) & 0x3) + 1)
            self.perm.append(((self.antenna_sel >> 2) & 0x3) + 1)
            self.perm.append(((self.antenna_sel >> 4) & 0x3) + 1)
            # print self.perm
            self.csi = self.parse_csi(self.unpacked[19:])

            # """ Set CSI """

    def set_csi(self, csi):
        self.csi = csi

        # """ Get CSI """

    def get_csi(self):
        return self.csi

        # """ Set number of TX elements """

    def set_tx(self, tx):
        self.Ntx = tx

        # """ Set number of RX elements """

    def set_rx(self, rx):
        self.Nrx = rx

        # """ Given raw_data (bytes) parse CSI complex values """

    def parse_csi(self, raw_data):
        index = 0
        remainder = 0
        # make a list of 30 elements
        csi = [None] * 30
        for i in range(0, self.nrs):
            index += 3
            remainder = (index % 8)

            Hx = np.matrix(np.zeros((self.Nrx, self.Ntx), complex))
            for r in range(0, self.Nrx):
                for t in range(0, self.Ntx):
                    #            first = struct.unpack("B",raw_data[index/8])[0] >> remainder
                    first = struct.unpack('B', bytes([raw_data[index // 8]]))[0] >> remainder
                    second = (struct.unpack('B', bytes([raw_data[index // 8 + 1]]))[0] << (8 - remainder))
                    tmp = (c_byte(first | second).value)
                    real = (c_double(tmp).value)
                    first = (struct.unpack('B', bytes([raw_data[index // 8 + 1]]))[0] >> remainder)
                    second = (struct.unpack('B', bytes([raw_data[index // 8 + 2]]))[0] << (8 - remainder))
                    tmp = (c_byte(first | second).value)
                    imag = (c_double(tmp).value)
                    index += 16
                    Hx.itemset((r, t), complex(real, imag))
            csi[i] = Hx
        return csi

    def __str__(self):
        return "NOISE(A,B,C)=[%d %d %d] Nrx=%d Ntx=%d RSSI(A,B,C)=[%d %d %d] Noise=%d AGC=%d" % (
            self.noise_a, self.noise_b, self.noise_c, self.Nrx, self.Ntx, self.rssi_a, self.rssi_b, self.rssi_c,
            self.noise,
            self.agc)

    # return 'Empty'
    def print_csi(self):
        i = 1
        for c in self.csi:
            print
            "%3d." % i,
            print(c),
            if (i % 9) == 0:
                print
                ""
            i += 1

            # """ Quantize the angle according to 802.11n standard
            #
            #    @orig      - angles being quantized (generated using compression see @compress)
            #    @which     - which angle is being quantized (psi or phi), psi by default
            #    @psi_bits  - number of bits used to represents PSI, possible values 1 2 3 or 4
            #
            #    @return    - a tuble containing the quantized angle and the k values
            # """

    def quantize(self, orig, which="psi", bits=3):
        if bits < 1 or bits > 4:
            raise Exception('psi_bits can be 1,2,3 or 4')

        a = float(2 ** (bits + 1));
        b = float(2 ** (bits + 2));
        psi = 0;

        if 'psi' is which:
            psi = 1
        elif 'phi' is which:
            psi = 0;
        else:
            raise Exception('Please speself.y either psi or phi\n');

        min = np.pi / bits ** b;

        if psi == 1:
            k_max = 2 ** (bits - 1)
        else:
            k_max = 2 ** (bits + 2) - 1;

        max = k_max * np.pi / a + np.pi / b;

        if orig <= min:
            quant_angle = min;
            k = 0;
            return (quant_angle, 0);

        if orig >= max:
            quant_angle = max;
            k = k_max;
            return (quant_angle, k)
        t = orig / np.pi * a - a / b

        k = np.ceil(t)
        quant_angle = k * np.pi / a + np.pi / b;

        return (quant_angle, k)

        # """ Helper method to quantize a list of set of angles (one set per subcarrier) """

    def quantize_angles(self, angles):
        l = len(angles)
        result = [None] * l

        for sc in range(l):
            sca = angles[sc]
            r = []
            for which, a in sca:
                r.append((which, self.quantize(a, which, 3)))
            result[sc] = r
        return result
        #
        # """ Given k values generated by quantization, it concatinates the bits do generate the bitpattern to be supplied to the card.
        #     Note: no need to reverse the order of angles as the function will do that.
        #     @k         - array of data as returned by quantize_angles function
        #     @psi_bits  - number of bits used to represent psi
        #
        #     @return - a tuple ([bits], bitpattern), where bits are the number of bits used to represent each angle
        # """

    def concatinate_bits(self, k, psi_bits=3):
        l = len(k)
        result = [None] * l

        # for every sub-carrier
        for sc in range(l):
            sck = k[sc]
            # need to reverse the order of angles as the last angles should end in the high order bits
            # so the order should be: psi_32, phi_22, psi_31, psi_21, phi_21, phi_11
            sck.reverse()
            r = []
            # get each k value (which,(quantized_angle, k_value))
            # which can either be 'psi' or 'phi'
            alength = len(sck)
            (w, (a, result)) = sck[0]
            result = int(result)
            bits = []
            if 'phi' is w:
                bits.append(psi_bits + 2)
            else:
                bits.append(psi_bits)

            for i in range(1, alength):
                (which, (a, kvalue)) = sck[i]

                bit = psi_bits
                if 'phi' is which:
                    bit = psi_bits + 2
                bits.append(bit)
                kvalue = int(kvalue)
                result = (result << bit)
                result += kvalue
            r.append((bits, result))
        return r

        # """
        #    Given a list of bit-string pattern as a tuple (([angle1_bits, angle2_bits, ..., anglen_bits]), bitpattern) it breaks the pattern into individual k values
        #
        #    @return - a tuple ([bits], [k-values])
        # """

    def break_bits(self, bitpatterns):
        l = len(bitpatterns)
        result = [None] * l
        # for every sub-carrier
        for sc in range(l):
            (bits, bitstring) = bitpatterns[sc];
            ks = []
            ## reverse the number of bits, since the last bitstring concatinated is the first one now
            bits.reverse()
            for b in bits:
                bitmask = 2 ** b - 1
                n = bitstring & bitmask
                ks.append(n)
                bitstring = bitstring >> b
            result[sc] = (bits, ks)

        return result
        #
        # """
        #    Compress and quantize CSI
        #    @psi_bits - the number of bits used to quantize psi
        # """

    def compress(self, psi_bits=3):
        if self.Ntx != 3:
            raise Exception('Only 3x3 configuration currently valid!')

        angles = np.angle(self.csi)
        length = len(angles)

        return_angles = [None] * length
        for i in range(length):
            DTilde = np.matrix(sp.eye(self.Ntx, dtype=complex))
            ## only 3x3 matrix currently so 6 angles
            quant_angles = []
            #     print len(angles)
            for tx in range(0, self.Ntx):
                ang = angles[i]
                DTilde[tx, tx] = np.exp(1j * ang[self.Nrx - 1, tx]);

            csi = self.csi[i]
            tmp = csi * DTilde.getH()
            phi_11 = np.angle(tmp[0, 0])
            if phi_11 < 0:
                phi_11 += 2 * np.pi

            phi_21 = np.angle(tmp[1, 0]);

            if phi_21 < 0:
                phi_21 += 2 * np.pi

            d1 = np.matrix(np.diag([np.exp(1j * phi_11), np.exp(1j * phi_21), 1]))

            tmp = d1.getH() * csi * DTilde.getH()

            x1 = tmp[0, 0]
            x2 = tmp[1, 0]
            psi_21 = self.calc_psi(x1, x2)

            G21 = np.matrix(sp.eye(self.Ntx, dtype=complex))
            G21[0, 0] = np.cos(psi_21)
            G21[0, 1] = np.sin(psi_21)
            G21[1, 0] = -np.sin(psi_21)
            G21[1, 1] = np.cos(psi_21)

            tmp = G21 * d1.getH() * csi * DTilde.getH()

            x1 = tmp[0, 0]
            x2 = tmp[2, 0]

            psi_31 = self.calc_psi(x1, x2)

            G31 = np.matrix(sp.eye(self.Ntx, dtype=complex))
            G31[0, 0] = np.cos(psi_31);
            G31[0, 2] = np.sin(psi_31);
            G31[2, 0] = -np.sin(psi_31);
            G31[2, 2] = np.cos(psi_31);

            V2 = G31 * G21 * d1.getH() * csi * DTilde.getH();
            phi_22 = np.angle(V2[1, 1])

            if phi_22 < 0:
                phi_22 += 2 * np.pi

            d2 = np.matrix(np.diag([1, np.exp(1j * phi_22), 1]))

            tmp = d2.getH() * V2;

            x1 = tmp[1, 1];
            x2 = tmp[2, 1];
            psi_32 = self.calc_psi(x1, x2)
            # ['phi11 ', 'phi21 ', 'psi21 ', 'psi31 ', 'phi22 ', 'psi32']
            return_angles[i] = [('phi', phi_11), ('phi', phi_21), ('psi', psi_21), ('psi', psi_31), ('phi', phi_22),
                                ('psi', psi_32)]
        return return_angles


        # """ Performs a Givens rotation """

    def calc_psi(self, x1, x2):
        y = np.sqrt([x1 ** 2 + x2 ** 2])
        return np.real(np.arccos(x1 / y))[0]

    def get_scaled_csi(self):
        rssi = []
        noise = []
        csi_sum = 0

        #        if self.rssi_a > 0:
        #           rssi.append(self.rssi_a)
        if self.rssi_b > 0:
            rssi.append(self.rssi_b)
        if self.rssi_c > 0:
            rssi.append(self.rssi_c)

        rssi = [r - 44 - self.agc for r in rssi]

        noise.append(self.noise_a)
        noise.append(self.noise_b)
        noise.append(self.noise_c)

        noise = [noise[i] for i in range(0, self.Nrx)]
        ref_noise = max(noise)

        noise_diff = [ref_noise - n for n in noise]
        noise_diff_abs = [np.power(10, n / 10) for n in noise_diff]
        ref_rssi = [r - ref_noise for r in rssi]

        rssi_sum = np.sum([pow(10, (r / 10)) for r in ref_rssi])
        # rssi_sum = numpy.sum(rssi_sum)

        for i in range(0, self.nrs):
            tmpAbs = np.abs(self.csi[0])
            csi_sum = csi_sum + np.sqrt(tmpAbs)

        common_scale = np.sqrt(rssi_sum / csi_sum * self.nrs)
        scale_per_rx = [common_scale * np.sqrt(n) for n in noise_diff_abs]

        ret = [None] * 30

        for j in range(0, self.nrs):
            tmpHx = self.csi[j]
            tmpRet = np.matrix(np.zeros((self.Ntx, self.Nrx), complex))
            for r in range(0, len(scale_per_rx)):
                for t in range(0, self.Ntx):
                    tmpVal = tmpHx.item((r, t)) * scale_per_rx[r]
                    tmpRet.itemset((t, r), tmpVal.item(0))
                    ret[j] = tmpRet
        return ret
