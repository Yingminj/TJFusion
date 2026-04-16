#include "FXMatrix.h"


FX_VOID FX_VectNorm(Vect3 a) 
{

	FX_DOUBLE r = FX_Sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2]);
	a[0] /= r;
	a[1] /= r;
	a[2] /= r;
}

FX_VOID	FX_Vect3AToB(Vect3 A, Vect3 B)
{
	B[0] = A[0];
	B[1] = A[1];
	B[2] = A[2];
}
FX_VOID FX_VectCross(Vect3 a, Vect3 b, Vect3 result)
{
	result[0] = a[1] * b[2] - a[2] * b[1];
	result[1] = a[2] * b[0] - a[0] * b[2];
	result[2] = a[0] * b[1] - a[1] * b[0];
}
FX_VOID	FX_VectAddToA(Vect3 a, Vect3 b)
{
	a[0] += b[0];
	a[1] += b[1];
	a[2] += b[2];
}
FX_VOID	FX_VectAdd(Vect3 a, Vect3 b, Vect3 result)
{
	result[0] = a[0] + b[0];
	result[1] = a[1] + b[1];
	result[2] = a[2] + b[2];
}
FX_VOID  FX_MMM33(Matrix3 L, Matrix3 R, Matrix3 Result)
{
	Result[0][0] = L[0][0] * R[0][0] + L[0][1] * R[1][0] + L[0][2] * R[2][0];
	Result[0][1] = L[0][0] * R[0][1] + L[0][1] * R[1][1] + L[0][2] * R[2][1];
	Result[0][2] = L[0][0] * R[0][2] + L[0][1] * R[1][2] + L[0][2] * R[2][2];

	Result[1][0] = L[1][0] * R[0][0] + L[1][1] * R[1][0] + L[1][2] * R[2][0];
	Result[1][1] = L[1][0] * R[0][1] + L[1][1] * R[1][1] + L[1][2] * R[2][1];
	Result[1][2] = L[1][0] * R[0][2] + L[1][1] * R[1][2] + L[1][2] * R[2][2];

	Result[2][0] = L[2][0] * R[0][0] + L[2][1] * R[1][0] + L[2][2] * R[2][0];
	Result[2][1] = L[2][0] * R[0][1] + L[2][1] * R[1][1] + L[2][2] * R[2][1];
	Result[2][2] = L[2][0] * R[0][2] + L[2][1] * R[1][2] + L[2][2] * R[2][2];
}

FX_VOID  FX_M33Trans(Matrix3 Org, Matrix3 Result)
{
	Result[0][0] = Org[0][0];
	Result[0][1] = Org[1][0];
	Result[0][2] = Org[2][0];

	Result[1][0] = Org[0][1];
	Result[1][1] = Org[1][1];
	Result[1][2] = Org[2][1];

	Result[2][0] = Org[0][2];
	Result[2][1] = Org[1][2];
	Result[2][2] = Org[2][2];
}
FX_VOID FX_PGPointMap(Matrix4 a_to_b, Vect3 in_a, Vect3 ret_in_b)
{
	ret_in_b[0] = a_to_b[0][3] + a_to_b[0][0] * in_a[0] + a_to_b[0][1] * in_a[1] + a_to_b[0][2] * in_a[2];
	ret_in_b[1] = a_to_b[1][3] + a_to_b[1][0] * in_a[0] + a_to_b[1][1] * in_a[1] + a_to_b[1][2] * in_a[2];
	ret_in_b[2] = a_to_b[2][3] + a_to_b[2][0] * in_a[0] + a_to_b[2][1] * in_a[1] + a_to_b[2][2] * in_a[2];
}

FX_VOID	FX_PGVectMap(Matrix4 a_to_b, Vect3 in_a, Vect3 ret_in_b)
{
	ret_in_b[0] = a_to_b[0][0] * in_a[0] + a_to_b[0][1] * in_a[1] + a_to_b[0][2] * in_a[2];
	ret_in_b[1] = a_to_b[1][0] * in_a[0] + a_to_b[1][1] * in_a[1] + a_to_b[1][2] * in_a[2];
	ret_in_b[2] = a_to_b[2][0] * in_a[0] + a_to_b[2][1] * in_a[1] + a_to_b[2][2] * in_a[2];
}


FX_VOID	FX_PGVectMapInv(Matrix4 a_to_b, Vect3 ret_in_a, Vect3 in_b)
{
	ret_in_a[0] = a_to_b[0][0] * in_b[0] + a_to_b[1][0] * in_b[1] + a_to_b[2][0] * in_b[2];
	ret_in_a[1] = a_to_b[0][1] * in_b[0] + a_to_b[1][1] * in_b[1] + a_to_b[2][1] * in_b[2];
	ret_in_a[2] = a_to_b[0][2] * in_b[0] + a_to_b[1][2] * in_b[1] + a_to_b[2][2] * in_b[2];
}



FX_VOID  FX_MMM44(Matrix4 L, Matrix4 R, Matrix4 Result)
{
	FX_INT32L i, j, k;
	for (i = 0; i < 4; i++)
	{
		for (j = 0; j < 4; j++)
		{
			Result[i][j] = 0;
			for (k = 0; k < 4; k++)
			{
				Result[i][j] += L[i][k] * R[k][j];
			}
		}
	}
}


FX_VOID  FX_PGMult(Matrix4 L, Matrix4 R, Matrix4 Result)
{
	Result[0][0] = L[0][0] * R[0][0] + L[0][1] * R[1][0] + L[0][2] * R[2][0];
	Result[0][1] = L[0][0] * R[0][1] + L[0][1] * R[1][1] + L[0][2] * R[2][1];
	Result[0][2] = L[0][0] * R[0][2] + L[0][1] * R[1][2] + L[0][2] * R[2][2];

	Result[1][0] = L[1][0] * R[0][0] + L[1][1] * R[1][0] + L[1][2] * R[2][0];
	Result[1][1] = L[1][0] * R[0][1] + L[1][1] * R[1][1] + L[1][2] * R[2][1];
	Result[1][2] = L[1][0] * R[0][2] + L[1][1] * R[1][2] + L[1][2] * R[2][2];

	Result[2][0] = L[2][0] * R[0][0] + L[2][1] * R[1][0] + L[2][2] * R[2][0];
	Result[2][1] = L[2][0] * R[0][1] + L[2][1] * R[1][1] + L[2][2] * R[2][1];
	Result[2][2] = L[2][0] * R[0][2] + L[2][1] * R[1][2] + L[2][2] * R[2][2];

	Result[0][3] = L[0][0] * R[0][3] + L[0][1] * R[1][3] + L[0][2] * R[2][3] + L[0][3];
	Result[1][3] = L[1][0] * R[0][3] + L[1][1] * R[1][3] + L[1][2] * R[2][3] + L[1][3];
	Result[2][3] = L[2][0] * R[0][3] + L[2][1] * R[1][3] + L[2][2] * R[2][3] + L[2][3];

	Result[3][0] = 0;
	Result[3][1] = 0;
	Result[3][2] = 0;
	Result[3][3] = 1;
}
FX_VOID	FX_PGGetGes(PosGes src, Matrix3 ges)
{
	FX_INT32L i, j;
	for (i = 0; i < 3; i++)
	{
		for (j = 0; j < 3; j++)
		{
			ges[i][j] = src[i][j];
		}
	}
}

FX_VOID	FX_PGGetPos(PosGes src, Vect3 pos)
{
	pos[0] = src[0][3];
	pos[1] = src[1][3];
	pos[2] = src[2][3];
}
FX_VOID	FX_PGGetAxisX(PosGes src, Vect3 axis_x)
{
	axis_x[0] = src[0][0];
	axis_x[1] = src[1][0];
	axis_x[2] = src[2][0];
}
FX_VOID	FX_PGGetAxisY(PosGes src, Vect3 axis_y)
{
	axis_y[0] = src[0][1];
	axis_y[1] = src[1][1];
	axis_y[2] = src[2][1];
}
FX_VOID	FX_PGGetAxisZ(PosGes src, Vect3 axis_z)
{
	axis_z[0] = src[0][2];
	axis_z[1] = src[1][2];
	axis_z[2] = src[2][2];
}
FX_VOID  FX_M44Copy(Matrix4 src, Matrix4 dst)
{
	FX_INT32L i, j;
	for (i = 0; i < 4; i++)
	{
		for (j = 0; j < 4; j++)
		{
			dst[i][j] = src[i][j];
		}
	}
}


FX_VOID  FX_M33Copy(Matrix3 src, Matrix3 dst)
{
	FX_INT32L i, j;
	for (i = 0; i < 3; i++)
	{
		for (j = 0; j < 3; j++)
		{
			dst[i][j] = src[i][j];
		}
	}
}


FX_VOID FX_PGMatrixInv(Matrix4 pg, Matrix4 pginv)
{
	pginv[0][0] = pg[0][0];
	pginv[0][1] = pg[1][0];
	pginv[0][2] = pg[2][0];

	pginv[1][0] = pg[0][1];
	pginv[1][1] = pg[1][1];
	pginv[1][2] = pg[2][1];

	pginv[2][0] = pg[0][2];
	pginv[2][1] = pg[1][2];
	pginv[2][2] = pg[2][2];

	pginv[3][0] = 0;
	pginv[3][1] = 0;
	pginv[3][2] = 0;
	pginv[3][3] = 1;

	FX_DOUBLE p[3];
	p[0] = pg[0][3];
	p[1] = pg[1][3];
	p[2] = pg[2][3];

	pginv[0][3] = -(pginv[0][0] * p[0] + pginv[0][1] * p[1] + pginv[0][2] * p[2]);
	pginv[1][3] = -(pginv[1][0] * p[0] + pginv[1][1] * p[1] + pginv[1][2] * p[2]);
	pginv[2][3] = -(pginv[2][0] * p[0] + pginv[2][1] * p[1] + pginv[2][2] * p[2]);
}


FX_VOID FX_MatRotAxis(Vect3 rot_dir, FX_DOUBLE rot_angle, Matrix3 m, Matrix3 m_roted)
{
	FX_DOUBLE r[3][3];
	FX_DOUBLE sinv;
	FX_DOUBLE cosv;

	FX_SIN_COS_DEG(rot_angle, &sinv, &cosv);
	FX_DOUBLE a = 1 - cosv;

	FX_DOUBLE kx = rot_dir[0];
	FX_DOUBLE ky = rot_dir[1];
	FX_DOUBLE kz = rot_dir[2];

	r[0][0] = cosv + a * kx * kx;		r[0][1] = -sinv * kz + a * kx * ky;		r[0][2] = sinv * ky + a * kx * kz;
	r[1][0] = sinv * kz + a * kx * ky;	r[1][1] = cosv + a * ky * ky;			r[1][2] = -sinv * kx + a * ky * kz;
	r[2][0] = -sinv * ky + a * kx * kz;	r[2][1] = sinv * kx + a * ky * kz;		r[2][2] = cosv + a * kz * kz;
	FX_MMM33(r, m, m_roted);
}

FX_BOOL FX_Matrix2ZYX(Matrix3 m, Vect3  ret)
{
	ret[1] = FX_ATan2(-m[2][0], FX_Sqrt(m[0][0] * m[0][0] + m[1][0] * m[1][0])) * FXARM_R2D;
	FX_DOUBLE cb = FX_COS_DEG(ret[1]);
	if (FX_Fabs(cb) > 0.05 * FXARM_D2R)
	{
		ret[0] = FX_ATan2(m[1][0] / cb, m[0][0] / cb) * FXARM_R2D;
		ret[2] = FX_ATan2(m[2][1] / cb, m[2][2] / cb) * FXARM_R2D;
		return FX_TRUE;
	}
	ret[0] = 0;
	ret[2] = 0;
	return FX_FALSE;

}

FX_BOOL FX_Matrix2ZYZ(Matrix3 m, Vect3  ret)
{
	ret[1] = FX_ATan2(FX_Sqrt(m[2][0] * m[2][0] + m[2][1] * m[2][1]), m[2][2]);
	FX_DOUBLE bsin = FX_SIN_ARC(ret[1]);
	if (FX_Fabs(ret[1]) < 0.05 * FXARM_D2R)
	{
		ret[0] = 0;
		ret[1] *= FXARM_R2D;
		ret[2] = FX_ATan2(-m[0][1], m[0][0]) * FXARM_R2D;
		return FX_FALSE;
	}
	ret[0] = FX_ATan2(m[1][2] / bsin, m[0][2] / bsin) * FXARM_R2D;
	ret[1] *= FXARM_R2D;
	ret[2] = FX_ATan2(m[2][1] / bsin, -m[2][0] / bsin) * FXARM_R2D;
	return FX_TRUE;
}

FX_VOID  FX_MMV3(Matrix3 L, Vect3 R, Vect3 Result)
{
	FX_INT32L i, j, k;
	for (i = 0; i < 3; i++)
	{
		Result[i] = 0;
		for (k = 0; k < 3; k++)
		{
			Result[i] += L[i][k] * R[k];
		}
	}
}


FX_VOID Tmat(FX_DOUBLE DH[4], Matrix4 T) 
{
	double c3 = FX_COS_DEG(DH[3]);
	double s3 = FX_SIN_DEG(DH[3]);
	double c0 = FX_COS_DEG(DH[0]);
	double s0 = FX_SIN_DEG(DH[0]);

	T[0][0] = c3; T[0][1] = -s3; T[0][2] = 0.0; T[0][3] = DH[1];
	T[1][0] = s3 * c0; T[1][1] = c3 * c0; T[1][2] = -s0; T[1][3] = -s0 * DH[2];
	T[2][0] = s3 * s0; T[2][1] = c3 * s0; T[2][2] = c0; T[2][3] = c0 * DH[2];
	T[3][0] = 0.0; T[3][1] = 0.0; T[3][2] = 0.0; T[3][3] = 1.0;
}


FX_VOID  FX_IdentM44(Matrix4 m)
{
	FX_INT32 i, j;
	for (i = 0; i < 4; i++) {
		for (j = 0; j < 4; j++) {
			m[i][j] = 0;
		}
		m[i][i] = 1;
	}
}


FX_VOID  FX_IdentM33(Matrix3 m)
{
	FX_INT32 i, j;
	for (i = 0; i < 3; i++) {
		for (j = 0; j < 3; j++) {
			m[i][j] = 0;
		}
		m[i][i] = 1;
	}
}